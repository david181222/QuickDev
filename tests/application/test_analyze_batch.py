"""El pipeline completo, con dobles en lugar de Gemini.

Los adaptadores reales son de `core/miguel` y todavia no existen. Estos dobles
implementan `LlmPort` y `PromptProvider`, que son los contratos que el Paso 0
dejo en `main`, asi que este archivo prueba el flujo de verdad: sin red, sin
clave y sin cuota. Es la prueba de que la arquitectura sirve para algo.

Cuando entren los adaptadores, estos dobles no se tiran: `FakeLlm` hara lo mismo
pero leyendo `crudo.json`.
"""

import pytest
from conftest import BASURA, BUG_PARED, BUILD

from quickdev.application.analyze_batch import PASOS, AnalyzeBatch
from quickdev.config import Settings
from quickdev.domain.models import FeedbackReport, PlaytestBatch, PlaytestComment
from quickdev.domain.rules.registry import rule_set
from quickdev.domain.validation import RepairPolicy, Validator
from quickdev.ports.llm import LlmRequest, LlmResponse, LlmTerminalError


class LlmDoble:
    """Devuelve las respuestas que se le den, en orden, y registra las peticiones."""

    def __init__(self, *respuestas: dict) -> None:
        self.respuestas = list(respuestas)
        self.peticiones: list[LlmRequest] = []

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self.peticiones.append(request)
        if not self.respuestas:
            raise LlmTerminalError("el doble se quedo sin respuestas preparadas")
        datos = self.respuestas.pop(0)
        return LlmResponse(data=datos, raw_text="", attempts=1, model="doble")


class PromptsDoble:
    def system_prompt(self, version: str) -> str:
        return f"prompt de prueba, version {version}"

    def build_payload(self, batch: PlaytestBatch) -> dict:
        return {
            "build": batch.build,
            "comentarios": [c.model_dump() for c in batch.comentarios],
        }


@pytest.fixture
def batch():
    return PlaytestBatch(
        build=BUILD,
        comentarios=[
            PlaytestComment(fuente="discord", texto=BUG_PARED),
            PlaytestComment(fuente="discord", texto=BASURA),
        ],
    )


def salida(**cambios) -> dict:
    """Una respuesta correcta del modelo para ese lote de 2 comentarios."""
    datos = {
        "resumen_general": "Un bug de colision y un comentario sin valor.",
        "sentimiento_general": "negativo",
        "version_juego": BUILD,
        "total_comentarios_analizados": 2,
        "requiere_revision_humana": True,
        "problemas_detectados": [
            {
                "categoria": "bugs",
                "descripcion": "El personaje se queda atascado en la pared del nivel 3.",
                "frecuencia": 1,
                "prioridad": "alta",
                "fuente_predominante": "discord",
            }
        ],
        "comentarios_evidencia": [{"texto": BUG_PARED, "fuente": "discord"}],
        "comentarios_descartados": [{"texto": BASURA, "motivo": "extremista"}],
    }
    datos.update(cambios)
    return datos


def construir(llm, repair_round: bool = False, reglas: str = "after") -> AnalyzeBatch:
    return AnalyzeBatch(
        llm=llm,
        validator=Validator(rule_set(reglas)),
        repair=RepairPolicy(),
        prompts=PromptsDoble(),
        settings=Settings(repair_round_enabled=repair_round, rules_version=reglas),
    )


# ---------------------------------------------------------------------------


def test_un_lote_limpio_pasa_sin_hallazgos(batch):
    llm = LlmDoble(salida())
    resultado = construir(llm).execute(batch)

    assert resultado.findings == []
    assert resultado.approved is True
    assert resultado.report.total_comentarios_analizados == 2
    assert len(llm.peticiones) == 1


def test_el_crudo_del_modelo_se_conserva_intacto(batch):
    """La diferencia entre crudo y corregido es lo que los evals necesitan."""
    llm = LlmDoble(salida(total_comentarios_analizados=99))
    resultado = construir(llm).execute(batch)

    assert resultado.raw_report["total_comentarios_analizados"] == 99
    assert resultado.report.total_comentarios_analizados == 2


def test_un_hallazgo_fuerza_revision_humana(batch):
    llm = LlmDoble(salida(total_comentarios_analizados=99, requiere_revision_humana=False))
    resultado = construir(llm).execute(batch)

    assert resultado.findings
    assert resultado.report.requiere_revision_humana is True
    assert resultado.approved is False


def test_el_esquema_se_le_pide_al_proveedor(batch):
    """ADR-0009: la forma la garantiza el proveedor, no una instruccion."""
    llm = LlmDoble(salida())
    construir(llm).execute(batch)

    assert llm.peticiones[0].response_schema is FeedbackReport


def test_la_traza_registra_los_cinco_pasos_en_orden(batch):
    llm = LlmDoble(salida())
    resultado = construir(llm).execute(batch)

    assert [p.name for p in resultado.trace.steps] == list(PASOS)


def test_la_traza_estampa_las_versiones_de_la_corrida(batch):
    """Sin este estampado, dos mediciones no son comparables."""
    llm = LlmDoble(salida())
    resultado = construir(llm, reglas="baseline").execute(batch)
    d = resultado.trace.to_dict()

    assert d["rules_version"] == "baseline"
    assert d["schema_version"] == "v1.1"
    assert d["model"]
    assert d["run_id"]


def test_una_respuesta_con_forma_invalida_falla_al_parsear(batch):
    """La forma se rechaza en la frontera, no se arrastra como hallazgo."""
    from pydantic import ValidationError

    llm = LlmDoble(salida(campo_inventado="x"))
    with pytest.raises(ValidationError):
        construir(llm).execute(batch)


# -- la ronda de reparacion, apagada por defecto ---------------------------


def test_la_ronda_de_reparacion_esta_apagada_por_defecto(batch):
    """Se enciende cuando una medicion de pass@1 vs pass@2 la justifique.

    `_env_file=None` a proposito: comprueba el default del CODIGO, no lo que
    tenga en su `.env` quien corra los tests.
    """
    assert Settings(_env_file=None).repair_round_enabled is False

    llm = LlmDoble(salida(total_comentarios_analizados=99), salida())
    construir(llm).execute(batch)

    assert len(llm.peticiones) == 1, "no debe haber segunda llamada"


def test_encendida_le_devuelve_los_hallazgos_al_modelo(batch):
    llm = LlmDoble(salida(total_comentarios_analizados=99), salida())
    resultado = construir(llm, repair_round=True).execute(batch)

    assert len(llm.peticiones) == 2
    reintento = llm.peticiones[1].payload
    assert "corregir_solo_estos_campos" in reintento
    assert reintento["corregir_solo_estos_campos"][0]["campo"] == "total_comentarios_analizados"
    assert resultado.findings == []
    assert [p.name for p in resultado.trace.steps if p.name == "repair_round"]


def test_si_el_reintento_no_mejora_se_queda_con_el_primero(batch):
    """Dos hallazgos antes y dos despues: el reintento no aporta, se descarta."""
    peor = salida(total_comentarios_analizados=77, version_juego="v9.9.9")
    llm = LlmDoble(salida(total_comentarios_analizados=99, version_juego="v9.9.9"), peor)
    resultado = construir(llm, repair_round=True).execute(batch)

    assert len(llm.peticiones) == 2
    assert resultado.raw_report["total_comentarios_analizados"] == 99


def test_si_el_reintento_falla_el_analisis_no_se_cae(batch):
    """Un fallo de la ronda extra no debe tumbar el camino de correccion por codigo."""
    llm = LlmDoble(salida(total_comentarios_analizados=99))  # solo una respuesta
    resultado = construir(llm, repair_round=True).execute(batch)

    assert resultado.report.total_comentarios_analizados == 2
    assert resultado.report.requiere_revision_humana is True
    descartada = [p for p in resultado.trace.steps if p.name == "repair_round"]
    assert descartada and "descartada" in descartada[0].decision

"""El paquete nuevo reproduce lo que hacia `evals/motor.py:validate_output`.

Es el test que sostiene todo el refactor. Sin el, "las reglas nuevas hacen lo
mismo que la funcion vieja" es una afirmacion; con el, es un dato.

Cubre TODOS los datos que existen en el repo, por las dos versiones del conjunto
de reglas:

  - las 7 regresiones deterministas
  - las 30 corridas reales de `evals/resultados/*/crudo.json`

Para cada caso se comparan dos cosas: la lista de mensajes -contenido y orden- y
los tres campos que la politica de reparacion puede tocar.

## Por que lee un fixture y no importa el codigo viejo

`tests/domain/equivalencia_baseline.json` contiene la salida de
`validate_output` congelada mientras ese codigo todavia existia. La primera
version de este test importaba `evals.motor` y `evals.casos` directamente, y eso
tenia un problema: `core/miguel` reescribe `evals/` y borra esos dos modulos, asi
que 223 tests se habrian puesto rojos en su rama sin que el hubiera roto nada.

Con el fixture, el test sobrevive a esa reescritura y conserva su valor
indefinidamente. El fixture no se regenera: el codigo que lo produjo desaparece,
asi que es evidencia historica, igual que `evals/resultados/baseline/`.
"""

import json
from pathlib import Path

import pytest

from quickdev.domain.models import FeedbackReport, PlaytestBatch, PlaytestComment
from quickdev.domain.rules.registry import RULE_SET_VERSIONS, rule_set
from quickdev.domain.validation import RepairPolicy, Validator

FIXTURE = Path(__file__).with_name("equivalencia_baseline.json")
CASOS = json.loads(FIXTURE.read_text(encoding="utf-8"))["casos"]
IDS = [c["nombre"] for c in CASOS]

# Diferencia conocida y aceptada, documentada en el ADR-0004.
#
# El validador viejo MUTABA `requiere_revision_humana` en medio de la deteccion:
# al encontrar un descarte por sesgo lo ponia en True inmediatamente, y eso hacia
# que la comprobacion siguiente -"se descartaron comentarios y no se marco
# revision humana"- ya no se cumpliera y su hallazgo se perdiera.
#
# Separar detectar de reparar hace que los dos hechos se reporten. El veredicto
# del caso no cambia; el conteo de hallazgos pasa de 1 a 2. Es mas informativo,
# no incorrecto: son dos razones distintas para lo mismo.
HALLAZGO_QUE_EL_VIEJO_SE_TRAGABA = "se descartaron comentarios y no se marco revision humana"


def _batch(caso: dict) -> PlaytestBatch:
    return PlaytestBatch(
        build=caso["build"],
        comentarios=[PlaytestComment(**c) for c in caso["lote"]],
    )


def _evaluar(caso: dict, modo: str):
    batch = _batch(caso)
    report = FeedbackReport.model_validate(caso["crudo"])
    hallazgos = Validator(rule_set(modo)).validate(report, batch)
    reparado = RepairPolicy().repair(report, batch, hallazgos)
    return report, batch, hallazgos, reparado


def test_el_fixture_tiene_los_casos_que_dice():
    """Si esto falla, el test no esta probando nada y los demas mienten."""
    assert len(CASOS) == 37, f"esperaba 37 casos, el fixture trae {len(CASOS)}"
    assert all(modo in c["esperado"] for c in CASOS for modo in RULE_SET_VERSIONS)


@pytest.mark.parametrize("modo", RULE_SET_VERSIONS)
@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_mismos_mensajes_y_en_el_mismo_orden(caso, modo):
    _, _, hallazgos, _ = _evaluar(caso, modo)
    nuevos = [h.message for h in hallazgos]
    esperados = caso["esperado"][modo]["fallos"]

    if nuevos == esperados:
        return

    # La UNICA divergencia admitida: en `after`, el hallazgo que el viejo se
    # tragaba aparece al final, porque su regla es la ultima del conjunto. Que la
    # excepcion sea exactamente esta -y no "contiene un mensaje mas"- es lo que
    # impide que este test tape cualquier otra diferencia.
    assert modo == "after", (
        f"el conjunto 'baseline' debe reproducir el validador viejo literalmente.\n"
        f"  viejo: {esperados}\n  nuevo: {nuevos}"
    )
    assert nuevos == [*esperados, HALLAZGO_QUE_EL_VIEJO_SE_TRAGABA], (
        f"divergencia no prevista.\n  viejo: {esperados}\n  nuevo: {nuevos}"
    )


@pytest.mark.parametrize("modo", RULE_SET_VERSIONS)
@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_misma_reparacion(caso, modo):
    _, _, _, reparado = _evaluar(caso, modo)
    esperado = caso["esperado"][modo]

    assert reparado.total_comentarios_analizados == esperado["total_comentarios_analizados"]
    assert reparado.version_juego == esperado["version_juego"]
    assert reparado.requiere_revision_humana == esperado["requiere_revision_humana"]


@pytest.mark.parametrize("modo", RULE_SET_VERSIONS)
@pytest.mark.parametrize("caso", CASOS, ids=IDS)
def test_lo_que_no_se_repara_no_se_toca(caso, modo):
    """La reparacion no inventa datos que faltan.

    Ni las frecuencias fuera de rango ni las citas no literales se corrigen: no
    se puede adivinar el valor correcto, y fabricarlo seria justo lo que el
    producto promete no hacer. Se reportan y se escala a una persona.
    """
    report, _, _, reparado = _evaluar(caso, modo)

    assert reparado.problemas_detectados == report.problemas_detectados
    assert reparado.comentarios_evidencia == report.comentarios_evidencia
    assert reparado.comentarios_descartados == report.comentarios_descartados
    assert reparado.resumen_general == report.resumen_general
    assert reparado.sentimiento_general == report.sentimiento_general

"""Las regresiones deterministas del validador. No llaman al modelo.

Responsabilidad: cada fila de `quickdev_regression_cases.csv` como un test
concreto, mas los dos casos que salieron del diagnostico y no estan en el CSV.

Lo que NO le corresponde: llamar a la API, ni saber nada de prompts. Estas 7
comprobaciones son gratis e instantaneas, y por eso son la puerta que corren las
tres ramas antes de abrir un PR (`scripts/gate_baseline.py`).

## Que cambio al reescribirlas

Antes se preguntaba por fragmentos de texto: `any("supera el total" in f for f in
fallos)`. Un test que busca subcadenas dentro de mensajes se rompe el dia que
alguien mejora la redaccion de un mensaje, y no se rompe el dia que la regla deja
de funcionar. Ahora se pregunta por `rule_id`, que es un identificador estable y
declarado como tal en `domain/rules/base.py`.

Lo que NO cambio son los resultados: los mismos 7 casos dan el mismo PASS/FAIL
que el CSV commiteado. Eso es lo que comprueba la puerta.
"""

from collections.abc import Callable
from dataclasses import dataclass

from evals.cases import LOTE_EDGE_VERSION, LOTE_NORMAL, VERSION_BUILD, lote
from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding
from quickdev.domain.rules.registry import rule_set
from quickdev.domain.validation import RepairPolicy, Validator


@dataclass(frozen=True)
class ResultadoValidacion:
    """Lo que se le pasa a la expectativa de un caso de regresion."""

    hallazgos: list[Finding]
    reparado: FeedbackReport

    @property
    def aprueba(self) -> bool:
        return not self.hallazgos

    @property
    def ids(self) -> set[str]:
        return {h.rule_id for h in self.hallazgos}


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    input_shape: str
    expected_check: str
    batch: PlaytestBatch
    output_simulado: dict
    espera: Callable[[ResultadoValidacion], bool]
    notes: str
    en_csv: bool = True


# ---------------------------------------------------------------------------
# Lotes y outputs sinteticos. Cada caso perturba UNA sola cosa del correcto.
# ---------------------------------------------------------------------------

LOTE_SIN_VERSION = lote(
    [
        ("discord", "El jefe final es demasiado dificil comparado con el resto del juego."),
        ("discord", "Hay un bug donde el personaje se queda atascado en la pared del nivel 3."),
    ],
    None,
)

LOTE_MISMO_BUG = lote(
    [
        ("discord", "Hay un bug donde el personaje se queda atascado en la pared del nivel 3."),
        ("steam", "Otra vez el bug de la pared en el nivel 3, ya van 3 veces que me pasa."),
    ],
    None,
)

LOTE_EXTREMISTA = lote(
    [
        ("discord", "Hay un bug donde el personaje se queda atascado en la pared del nivel 3."),
        ("discord", "Este juego es una basura total, quien lo hizo no tiene idea de nada."),
    ],
    None,
)


def _output_valido(batch: PlaytestBatch) -> dict:
    """Output sintetico correcto para ese lote."""
    indice_evidencia = 3 if batch.total > 3 else 0
    return {
        "resumen_general": "Reporte de prueba.",
        "sentimiento_general": "negativo",
        "version_juego": batch.build,
        "total_comentarios_analizados": batch.total,
        "requiere_revision_humana": False,
        "problemas_detectados": [
            {
                "categoria": "bugs",
                "descripcion": "El personaje se queda atascado en la pared del nivel 3.",
                "frecuencia": 2,
                "prioridad": "alta",
                "fuente_predominante": "discord",
            }
        ],
        "comentarios_evidencia": [
            {"texto": batch.texto_de(indice_evidencia), "fuente": "discord"}
        ],
        "comentarios_descartados": [],
    }


def _con(base: dict, **cambios) -> dict:
    salida = dict(base)
    salida.update(cambios)
    return salida


_FRECUENCIA_DESBORDADA = _con(
    _output_valido(LOTE_MISMO_BUG),
    problemas_detectados=[
        {
            "categoria": "bugs",
            "descripcion": "Bug de pared en el nivel 3.",
            "frecuencia": 99,  # supera el total de 2
            "prioridad": "alta",
            "fuente_predominante": "discord",
        }
    ],
)


def _sin_hallazgos(r: ResultadoValidacion) -> bool:
    return r.aprueba


def _detecta(rule_id: str) -> Callable[[ResultadoValidacion], bool]:
    return lambda r: rule_id in r.ids


# ---------------------------------------------------------------------------
# Los 7 casos
# ---------------------------------------------------------------------------

REGRESIONES: tuple[RegressionCase, ...] = (
    RegressionCase(
        "happy_path",
        "14 comentarios con version explicita v0.8.2",
        "Debe conservar conteo real, citas literales y version literal.",
        LOTE_NORMAL,
        _output_valido(LOTE_NORMAL),
        _sin_hallazgos,
        "Un output correcto no debe generar ningun fallo.",
    ),
    RegressionCase(
        "missing_version",
        "Comentarios sin version de build",
        "version_juego debe ser null y requiere_revision_humana true.",
        LOTE_SIN_VERSION,
        _con(_output_valido(LOTE_SIN_VERSION), version_juego="v1.0"),
        lambda r: (
            r.reparado.version_juego is None
            and r.reparado.requiere_revision_humana is True
            and "version_appears_literally" in r.ids
        ),
        "No inferir version.",
    ),
    RegressionCase(
        "frequency_overflow",
        "2 comentarios sobre el mismo bug",
        "Ninguna frecuencia puede superar total_comentarios_analizados.",
        LOTE_MISMO_BUG,
        _FRECUENCIA_DESBORDADA,
        _detecta("frequency_within_total"),
        "Evita metricas inventadas.",
    ),
    RegressionCase(
        "non_literal_evidence",
        "Output cita texto que no aparece en input",
        "La validacion debe fallar por evidencia no literal.",
        LOTE_NORMAL,
        _con(
            _output_valido(LOTE_NORMAL),
            comentarios_evidencia=[
                {
                    "texto": "Los jugadores estan muy molestos con el sistema de guardado.",
                    "fuente": "discord",
                }
            ],
        ),
        _detecta("quotes_are_literal"),
        "Protege auditabilidad.",
    ),
    RegressionCase(
        "discarded_bias",
        "Comentario extremista o sesgado",
        "Debe ir a comentarios_descartados y forzar revision humana.",
        LOTE_EXTREMISTA,
        _con(
            _output_valido(LOTE_EXTREMISTA),
            requiere_revision_humana=False,
            comentarios_descartados=[
                {
                    "texto": (
                        "Este juego es una basura total, quien lo hizo no tiene idea de nada."
                    ),
                    "motivo": "extremista",
                }
            ],
        ),
        lambda r: (
            r.reparado.requiere_revision_humana is True
            and "discarded_bias_requires_review" in r.ids
        ),
        "Human-in-the-loop obligatorio.",
    ),
    # Fuera del CSV: salio del diagnostico del baseline.
    RegressionCase(
        "version_ausente_legitima",
        "Lote sin versión, output con version_juego null (correcto)",
        "No debe reportarse ningún fallo: la ausencia de versión no es un error.",
        LOTE_SIN_VERSION,
        _output_valido(LOTE_SIN_VERSION),
        _sin_hallazgos,
        "Expone el falso positivo del validador baseline.",
        en_csv=False,
    ),
    # Fuera del CSV: es el edge case del producto, verificado sin llamar al modelo.
    RegressionCase(
        "version_de_otro_build",
        "Build v0.8.2 pero el output cita la v0.5 de un comentario",
        "version_juego debe ser la build analizada, no una versión citada dentro del feedback.",
        LOTE_EDGE_VERSION,
        _con(
            _output_valido(LOTE_EDGE_VERSION),
            version_juego="v0.5",
            requiere_revision_humana=True,
        ),
        lambda r: r.reparado.version_juego == VERSION_BUILD,
        "Lo que el validador baseline no podía atrapar.",
        en_csv=False,
    ),
)


def validar(caso: RegressionCase, modo: str) -> ResultadoValidacion:
    """Corre el validador de esa version sobre el output sintetico del caso."""
    validator = Validator(rule_set(modo))
    reporte = FeedbackReport.model_validate(caso.output_simulado)
    hallazgos = validator.validate(reporte, caso.batch)
    reparado = RepairPolicy().repair(reporte, caso.batch, hallazgos)
    return ResultadoValidacion(hallazgos=hallazgos, reparado=reparado)


def run_regresiones(modo: str = "baseline") -> list[dict]:
    """Las 7 filas del reporte de regresion, en el orden de siempre.

    La firma y la forma de las filas se conservan porque `scripts/gate_baseline.py`
    las consume, y esa puerta la corren las tres ramas.
    """
    filas = []
    for caso in REGRESIONES:
        r = validar(caso, modo)
        filas.append(
            {
                "case_id": caso.case_id,
                "en_csv": caso.en_csv,
                "input_shape": caso.input_shape,
                "expected_check": caso.expected_check,
                "pass_fail": "PASS" if bool(caso.espera(r)) else "FAIL",
                "fallos_detectados": len(r.hallazgos),
                "detalle": "; ".join(h.message for h in r.hallazgos[:3]),
                "notes": caso.notes,
            }
        )
    return filas


# Se expone para que `reporting.py` no tenga que importar la lista entera.
POR_ID: dict[str, RegressionCase] = {c.case_id: c for c in REGRESIONES}

__all__ = ["POR_ID", "REGRESIONES", "RegressionCase", "run_regresiones", "validar"]

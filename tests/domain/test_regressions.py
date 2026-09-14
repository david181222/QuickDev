"""Las 7 regresiones del harness, como tests de pytest sobre el paquete nuevo.

Vienen de `evals/casos.py:REGRESIONES`, donde eran una lista de dataclasses que
un runner propio recorria. Aqui son `@pytest.mark.parametrize`, asi que se puede
correr una sola (`pytest -k frequency_overflow`), el reporte de fallo lo da
pytest, y un CI puede bloquear un PR con ellas.

NO llaman al modelo. Cada caso parte de un output sintetico correcto y perturba
una sola cosa, para comprobar que la validacion atrapa justo eso. Son
deterministas, gratis e instantaneas: una suite que cuesta dinero no se corre, y
una suite que no se corre no protege nada.

Los veredictos esperados son los que estan COMMITEADOS en
`evals/resultados/<modo>/regresion.csv`. Si uno cambia, la mejora medida del
proyecto deja de ser comparable.
"""

import pytest
from conftest import (
    BASURA,
    BUG_PARED,
    BUILD,
    CITA_V05,
    INVENTARIO,
    JEFE_FINAL,
    JEFE_ROTO,
    OTRA_VEZ,
)

from quickdev.domain.models import FeedbackReport, PlaytestBatch, PlaytestComment
from quickdev.domain.rules.registry import rule_set
from quickdev.domain.validation import RepairPolicy, Validator

# ---------------------------------------------------------------------------
# Los lotes de cada escenario
# ---------------------------------------------------------------------------


def _batch(pares: list[tuple[str, str]], build: str | None) -> PlaytestBatch:
    return PlaytestBatch(
        build=build,
        comentarios=[PlaytestComment(fuente=f, texto=t) for f, t in pares],
    )


SIN_VERSION = _batch([("discord", JEFE_FINAL), ("discord", BUG_PARED)], None)
MISMO_BUG = _batch([("discord", BUG_PARED), ("steam", OTRA_VEZ)], None)
EXTREMISTA = _batch([("discord", BUG_PARED), ("discord", BASURA)], None)
EDGE_VERSION = _batch([("discord", JEFE_ROTO), ("discord", CITA_V05), ("steam", INVENTARIO)], BUILD)
NORMAL = _batch([("discord", BUG_PARED), ("steam", OTRA_VEZ)], BUILD)


def _reporte(batch: PlaytestBatch, **cambios) -> FeedbackReport:
    datos = {
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
        "comentarios_evidencia": [{"texto": BUG_PARED, "fuente": "discord"}],
        "comentarios_descartados": [],
    }
    datos.update(cambios)
    return FeedbackReport.model_validate(datos)


# ---------------------------------------------------------------------------
# Los 7 casos: (id, batch, reporte perturbado, comprobacion, esperado por modo)
# ---------------------------------------------------------------------------


def _sin_hallazgos(hallazgos, reparado, batch):
    return not hallazgos


def _con_mensaje(fragmento):
    def check(hallazgos, reparado, batch):
        return any(fragmento in h.message for h in hallazgos)

    return check


def _version_null_y_revision(hallazgos, reparado, batch):
    return (
        reparado.version_juego is None
        and reparado.requiere_revision_humana is True
        and any("no aparece literalmente" in h.message for h in hallazgos)
    )


def _revision_por_sesgo(hallazgos, reparado, batch):
    return reparado.requiere_revision_humana is True and any(
        "sesgados o extremistas" in h.message for h in hallazgos
    )


def _version_es_la_build(hallazgos, reparado, batch):
    return reparado.version_juego == BUILD


# esperado: (baseline, after) segun evals/resultados/*/regresion.csv
CASOS = [
    pytest.param(NORMAL, _reporte(NORMAL), _sin_hallazgos, ("PASS", "PASS"), id="happy_path"),
    pytest.param(
        SIN_VERSION,
        _reporte(SIN_VERSION, version_juego="v1.0"),
        _version_null_y_revision,
        ("PASS", "PASS"),
        id="missing_version",
    ),
    pytest.param(
        MISMO_BUG,
        _reporte(
            MISMO_BUG,
            problemas_detectados=[
                {
                    "categoria": "bugs",
                    "descripcion": "Bug de pared en el nivel 3.",
                    "frecuencia": 99,
                    "prioridad": "alta",
                    "fuente_predominante": "discord",
                }
            ],
        ),
        _con_mensaje("supera el total"),
        ("PASS", "PASS"),
        id="frequency_overflow",
    ),
    pytest.param(
        NORMAL,
        _reporte(
            NORMAL,
            comentarios_evidencia=[
                {
                    "texto": "Los jugadores estan muy molestos con el sistema de guardado.",
                    "fuente": "discord",
                }
            ],
        ),
        _con_mensaje("no existe en el lote"),
        ("PASS", "PASS"),
        id="non_literal_evidence",
    ),
    pytest.param(
        EXTREMISTA,
        _reporte(
            EXTREMISTA,
            requiere_revision_humana=False,
            comentarios_descartados=[{"texto": BASURA, "motivo": "extremista"}],
        ),
        _revision_por_sesgo,
        ("PASS", "PASS"),
        id="discarded_bias",
    ),
    # Los dos ultimos salieron del diagnostico y son la prueba de la mejora:
    # FAIL en baseline, PASS en after. Si alguna vez pasan en baseline, alguien
    # "arreglo" la referencia y la comparacion dejo de significar nada.
    pytest.param(
        SIN_VERSION,
        _reporte(SIN_VERSION),
        _sin_hallazgos,
        ("FAIL", "PASS"),
        id="version_ausente_legitima",
    ),
    pytest.param(
        EDGE_VERSION,
        _reporte(EDGE_VERSION, version_juego="v0.5", requiere_revision_humana=True),
        _version_es_la_build,
        ("FAIL", "PASS"),
        id="version_de_otro_build",
    ),
]


@pytest.mark.parametrize(("batch", "report", "comprobar", "esperado"), CASOS)
@pytest.mark.parametrize("modo", ["baseline", "after"])
def test_regresion(modo, batch, report, comprobar, esperado):
    validator = Validator(rule_set(modo))
    hallazgos = validator.validate(report, batch)
    reparado = RepairPolicy().repair(report, batch, hallazgos)

    resultado = "PASS" if comprobar(hallazgos, reparado, batch) else "FAIL"
    esperado_del_modo = esperado[0] if modo == "baseline" else esperado[1]
    assert resultado == esperado_del_modo, (
        f"el conjunto de reglas '{modo}' dio {resultado} y la medicion "
        f"commiteada dice {esperado_del_modo}. Hallazgos: "
        f"{[h.message for h in hallazgos]}"
    )


def test_la_mejora_medida_sigue_siendo_real():
    """after arregla exactamente dos casos que baseline no podia atrapar."""
    mejoran = [c.id for c in CASOS if c.values[3] == ("FAIL", "PASS")]
    assert mejoran == ["version_ausente_legitima", "version_de_otro_build"]

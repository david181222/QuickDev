"""El contrato de salida no cambia sin que alguien lo decida.

Estos tests protegen la decision D3 del plan: el esquema evoluciona de forma
aditiva y los ocho campos existentes conservan nombre y semantica. Si alguien
renombra `requiere_revision_humana`, las mediciones de `evals/resultados/` dejan
de ser comparables y hay que generar una linea base nueva. Es una decision
legitima, pero tiene que ser deliberada: eso es lo que este archivo obliga.

`core/edwin` amplia esto con un golden file del schema completo y con un test por
regla de validacion.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from quickdev.domain.models import (
    CONTRACT_FIELDS,
    SCHEMA_VERSION,
    DetectedIssue,
    FeedbackReport,
    PlaytestBatch,
    PlaytestComment,
)

GOLDEN = Path(__file__).with_name("golden_schema.json")

# Los ocho nombres del esquema congelado, escritos a mano a proposito. Que este
# literal y el modelo tengan que coincidir es justamente la proteccion.
CAMPOS_ESPERADOS = {
    "resumen_general",
    "sentimiento_general",
    "version_juego",
    "total_comentarios_analizados",
    "requiere_revision_humana",
    "problemas_detectados",
    "comentarios_evidencia",
    "comentarios_descartados",
}


def _reporte_valido(**cambios) -> dict:
    base = {
        "resumen_general": "Reporte de prueba.",
        "sentimiento_general": "negativo",
        "version_juego": "v0.8.2",
        "total_comentarios_analizados": 2,
        "requiere_revision_humana": False,
        "problemas_detectados": [],
        "comentarios_evidencia": [],
        "comentarios_descartados": [],
    }
    base.update(cambios)
    return base


def test_el_reporte_tiene_exactamente_los_ocho_campos_del_contrato():
    assert set(FeedbackReport.model_fields) == CAMPOS_ESPERADOS


def test_la_constante_del_contrato_coincide_con_el_modelo():
    assert set(CONTRACT_FIELDS) == set(FeedbackReport.model_fields)


def test_un_campo_no_declarado_es_error_de_parseo_no_hallazgo_de_validacion():
    """La forma se comprueba en la frontera, no mas adentro. Ver ADR-0009."""
    with pytest.raises(ValidationError):
        FeedbackReport.model_validate(_reporte_valido(campo_inventado="x"))


@pytest.mark.parametrize("campo", sorted(CAMPOS_ESPERADOS))
def test_los_ocho_campos_son_requeridos(campo):
    """Ninguno tiene default: omitir uno es un error, no un vacio silencioso.

    Reproduce en la frontera la comprobacion original
    `set(output.keys()) == REQUIRED_FIELDS`.
    """
    incompleto = _reporte_valido()
    del incompleto[campo]
    with pytest.raises(ValidationError):
        FeedbackReport.model_validate(incompleto)


def test_version_juego_es_requerido_pero_admite_null():
    """El modelo tiene que pronunciarse sobre la version, aunque sea con null."""
    reporte = FeedbackReport.model_validate(_reporte_valido(version_juego=None))
    assert reporte.version_juego is None


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("sentimiento_general", "eufórico"),
        ("total_comentarios_analizados", -1),
        ("resumen_general", "x" * 401),
    ],
)
def test_el_esquema_rechaza_valores_fuera_del_vocabulario(campo, valor):
    with pytest.raises(ValidationError):
        FeedbackReport.model_validate(_reporte_valido(**{campo: valor}))


def test_evidencia_idx_es_aditivo_y_opcional():
    """Un problema sin `evidencia_idx` sigue siendo valido: v1.1 lee JSON de v1."""
    issue = DetectedIssue.model_validate(
        {
            "categoria": "bugs",
            "descripcion": "El personaje se queda atascado en la pared del nivel 3.",
            "frecuencia": 2,
            "prioridad": "alta",
            "fuente_predominante": "discord",
        }
    )
    assert issue.evidencia_idx == []
    assert SCHEMA_VERSION.startswith("v1")


def test_el_total_del_lote_lo_calcula_el_codigo():
    """`PlaytestBatch.total` es la unica fuente de verdad sobre el conteo."""
    batch = PlaytestBatch(
        build="v0.8.2",
        comentarios=[
            PlaytestComment(fuente="discord", texto="Hay un bug en el nivel 3."),
            PlaytestComment(fuente="steam", texto="El jefe final es injusto."),
        ],
    )
    assert batch.total == 2
    assert batch.texto_de(1) == "El jefe final es injusto."


def test_un_comentario_vacio_no_es_un_comentario():
    """Regla del contrato ('el comentario no puede estar vacio') a nivel de tipo."""
    with pytest.raises(ValidationError):
        PlaytestComment(fuente="discord", texto="")


def test_build_no_especificada_es_none_no_cadena_vacia():
    """La distincion que el edge case de version necesitaba."""
    assert PlaytestBatch().build is None


def test_el_schema_derivado_coincide_con_el_golden_file():
    """Detecta cambios de TIPO, no solo de nombre.

    Los tests de arriba protegen los nombres de los 8 campos. Este protege la
    forma completa: si alguien afloja un enum, quita un `max_length` o cambia
    `int` por `str`, el diff salta aqui.

    Para regenerarlo a proposito, despues de decidir el cambio y anotarlo en un
    ADR:

        python -c "import json;from quickdev.domain.models import FeedbackReport as R;\
print(json.dumps(R.model_json_schema(),indent=2,ensure_ascii=False,sort_keys=True))" \
            > tests/domain/golden_schema.json
    """
    actual = FeedbackReport.model_json_schema()
    esperado = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert actual == esperado, (
        "el esquema de salida cambio. Si es deliberado, regenera el golden file "
        "y documenta el cambio en un ADR: renombrar o cambiar el tipo de un "
        "campo invalida las mediciones de evals/resultados/."
    )

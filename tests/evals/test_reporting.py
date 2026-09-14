"""Donde se escriben los resultados. El bug de sobrescritura, cerrado con tests.

`motor.py:566` devolvia siempre `resultados/<modo>/` y escribia encima. Volver a
correr los evals borraba la medicion anterior. Ver ADR-0007.
"""

import csv
import json

import pytest

from evals.reporting import directorio_de_corrida, escribir_salidas
from quickdev.observability.manifest import RunManifest


def manifiesto(prompt="baseline", reglas="baseline", n=3) -> RunManifest:
    return RunManifest(
        prompt_version=prompt,
        rules_version=reglas,
        schema_version="v1.1",
        model="replay",
        n_corridas=n,
        git_sha="abc1234",
    )


FILA = {
    "eval_id": "happy_path",
    "categoria": "1. Happy path",
    "corrida": 1,
    "paso": True,
    "fallos_validacion": 0,
    "tool_ok": True,
    "intentos": 1,
    "from_cache": False,
    "truncado": False,
    "latencia_s": 1.2,
    "asserts_crudo": {},
    "asserts_corregido": {},
    "detalle_hallazgos": [],
    "input": "Lote de playtest, build v0.8.2:\n1. (steam) \"x\"",
    "output_crudo": {"total_comentarios_analizados": 1},
    "output_corregido": {"total_comentarios_analizados": 1},
    "trace": None,
}

DIAGNOSTICO = {
    "eval_id": "happy_path",
    "categoria": "1. Happy path",
    "hipotesis": "una hipotesis",
    "corridas": 3,
    "corridas_esperadas": 3,
    "corridas_completas": True,
    "tasa": "3/3",
    "detalle_asserts": {},
    "errores_de_asercion": [],
    "umbrales": {"min_corridas": 5, "fraccion_minima": 0.2},
    "preguntas": {
        "¿Falló el prompt?": {"respuesta": "NO", "evidencia": "ninguna"},
        "¿Faltó contexto?": {
            "respuesta": "NO",
            "evidencia": "ninguna",
            "derivada_de": "¿Falló el prompt?",
        },
    },
}

REGRESIONES = [
    {
        "case_id": "happy_path",
        "en_csv": True,
        "input_shape": "x",
        "expected_check": "y",
        "pass_fail": "PASS",
        "fallos_detectados": 0,
        "detalle": "",
        "notes": "z",
    }
]


# ---------------------------------------------------------------------------
# El directorio
# ---------------------------------------------------------------------------


def test_el_nombre_lleva_fecha_prompt_y_reglas(tmp_path):
    m = manifiesto(prompt="after", reglas="baseline")

    destino = directorio_de_corrida(m, raiz=tmp_path)

    assert destino.name.endswith("-after-baseline")
    assert destino.name[:10] == m.started_at[:10]


def test_dos_corridas_el_mismo_dia_no_colisionan(tmp_path):
    """Sin el sufijo, correr dos veces hoy volveria a pisar la medicion de hoy."""
    m = manifiesto()

    primera = directorio_de_corrida(m, raiz=tmp_path)
    primera.mkdir(parents=True)
    segunda = directorio_de_corrida(m, raiz=tmp_path)

    assert segunda != primera
    assert segunda.name == f"{primera.name}-2"


@pytest.mark.parametrize("historico", ["baseline", "after"])
def test_escribir_sobre_una_medicion_commiteada_es_un_error(tmp_path, historico):
    """La proteccion explicita: son el registro historico, no un destino de salida."""
    with pytest.raises(ValueError, match="no se sobrescribe"):
        escribir_salidas(
            tmp_path / historico, [FILA], [DIAGNOSTICO], REGRESIONES, manifiesto()
        )


# ---------------------------------------------------------------------------
# Los archivos
# ---------------------------------------------------------------------------


@pytest.fixture
def corrida_escrita(tmp_path):
    m = manifiesto()
    destino = escribir_salidas(
        tmp_path / "corrida", [FILA], [DIAGNOSTICO], REGRESIONES, m
    )
    return destino


def test_escribe_los_cinco_artefactos(corrida_escrita):
    esperados = {
        "resultados.csv",
        "crudo.json",
        "regresion.csv",
        "diagnostico.md",
        "manifiesto.json",
    }

    assert {p.name for p in corrida_escrita.iterdir()} == esperados


def test_el_crudo_sirve_para_replay(corrida_escrita):
    """El formato tiene que ser el mismo que el de `baseline/crudo.json`."""
    crudo = json.loads((corrida_escrita / "crudo.json").read_text(encoding="utf-8"))

    assert "happy_path_run1" in crudo
    assert crudo["happy_path_run1"]["input"] == FILA["input"]
    assert crudo["happy_path_run1"]["output_crudo"] == FILA["output_crudo"]


def test_el_diagnostico_lleva_el_estampado(corrida_escrita):
    """Un diagnostico sin manifiesto no se puede comparar con otro."""
    md = (corrida_escrita / "diagnostico.md").read_text(encoding="utf-8")

    assert "abc1234" in md, "el commit"
    assert "`baseline`" in md, "las versiones"
    assert "run_id" in md


def test_el_diagnostico_marca_la_pregunta_derivada(corrida_escrita):
    md = (corrida_escrita / "diagnostico.md").read_text(encoding="utf-8")

    assert "no es una señal independiente" in md


def test_el_csv_de_resultados_tiene_las_columnas_esperadas(corrida_escrita):
    with open(corrida_escrita / "resultados.csv", encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))

    assert filas[0]["eval_id"] == "happy_path"
    assert "asserts_con_error" in filas[0], "el tercer estado tiene columna propia"
    assert "from_cache" in filas[0]


def test_el_manifiesto_es_json_legible(corrida_escrita):
    m = json.loads((corrida_escrita / "manifiesto.json").read_text(encoding="utf-8"))

    assert m["versiones"]["git_sha"] == "abc1234"
    assert m["corridas"] == 3

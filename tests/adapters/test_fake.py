"""El FakeLlm reproduciendo las mediciones reales de `evals/resultados/`.

Estos tests leen los archivos commiteados de verdad, no fixtures inventadas. Es
deliberado: si el replay dejara de reproducir el baseline, el fallo tiene que
salir aqui y no tres pasos mas adelante, en la puerta de aceptacion.
"""

import json
from pathlib import Path

import pytest

from quickdev.adapters.fake import FakeLlm, SinRespuestaGrabada, _orden_de_corrida
from quickdev.ports.llm import LlmRequest

RESULTADOS = Path(__file__).resolve().parents[2] / "evals" / "resultados"
CRUDO_BASELINE = RESULTADOS / "baseline" / "crudo.json"
CRUDO_AFTER = RESULTADOS / "after" / "crudo.json"

# Se lee una vez: los tests comparan contra la medicion commiteada, no contra
# una copia inventada aqui.
CRUDO = json.loads(CRUDO_BASELINE.read_text(encoding="utf-8"))
ENTRADA_HAPPY = CRUDO["happy_path_run1"]["input"]


@pytest.fixture
def fake_baseline() -> FakeLlm:
    return FakeLlm.from_crudo(CRUDO_BASELINE)


def pedir(fake: FakeLlm, entrada: str):
    return fake.complete_json(LlmRequest(system_prompt="sp", payload={"input": entrada}))


# ---------------------------------------------------------------------------
# Reproduce lo medido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("archivo", [CRUDO_BASELINE, CRUDO_AFTER])
def test_carga_las_dos_mediciones_commiteadas(archivo):
    fake = FakeLlm.from_crudo(archivo)

    assert len(fake.respuestas) == 5, "los 5 evals del producto"
    assert fake.max_corridas == 3, "n=3, que es como se midieron"


def test_devuelve_exactamente_el_output_guardado(fake_baseline):
    registro = CRUDO["happy_path_run1"]

    r = pedir(fake_baseline, registro["input"])

    assert r.data == registro["output_crudo"]


def test_reproduce_los_metadatos_de_la_tool(fake_baseline):
    """Los intentos y la latencia medidos aquel dia siguen siendo los de la corrida."""
    registro = CRUDO["happy_path_run1"]

    r = pedir(fake_baseline, registro["input"])

    assert r.attempts == registro["meta_tool"]["intentos"]
    assert r.latency_s == registro["meta_tool"]["latencia_s"]
    assert r.from_cache is False


def test_llamadas_sucesivas_avanzan_por_las_corridas(fake_baseline):
    """Tres llamadas dan run1, run2 y run3, no tres veces run1.

    Si devolviera siempre la primera, la pregunta "el resultado es inestable
    entre corridas?" respondaria NO siempre en replay, y esa es justo la senal
    que el diagnostico necesita conservar.
    """
    entrada = ENTRADA_HAPPY

    salidas = [pedir(fake_baseline, entrada).data for _ in range(3)]

    assert salidas == [CRUDO[f"happy_path_run{i}"]["output_crudo"] for i in (1, 2, 3)]


def test_el_modelo_dice_replay(fake_baseline):
    """Ningun reporte debe poder confundir una reproduccion con una medicion nueva."""
    assert pedir(fake_baseline, ENTRADA_HAPPY).model == "replay"


# ---------------------------------------------------------------------------
# Falla ruidosamente: el bug de motor.py:429-431
# ---------------------------------------------------------------------------


def test_un_input_desconocido_es_un_error_no_un_silencio(fake_baseline):
    with pytest.raises(SinRespuestaGrabada, match="No hay ninguna corrida grabada"):
        pedir(fake_baseline, "un lote que nunca se midio")


def test_pedir_mas_corridas_de_las_grabadas_es_un_error(fake_baseline):
    """El defecto que hacia que "2/2" y "2/3" se vieran igual de bien.

    `motor.py:429-431` hacia `continue` y `n = len(filas)` se encogia en
    silencio. Aqui, pedir n=4 sobre un archivo con 3 corridas se ve.
    """
    entrada = ENTRADA_HAPPY
    for _ in range(3):
        pedir(fake_baseline, entrada)

    with pytest.raises(SinRespuestaGrabada, match="solo hay 3 grabadas"):
        pedir(fake_baseline, entrada)


def test_un_archivo_sin_corridas_utiles_no_construye(tmp_path):
    vacio = tmp_path / "crudo.json"
    vacio.write_text('{"caso_run1": {"meta_tool": {}}}', encoding="utf-8")

    with pytest.raises(SinRespuestaGrabada):
        FakeLlm.from_crudo(vacio)


# ---------------------------------------------------------------------------
# Detalles que muerden
# ---------------------------------------------------------------------------


def test_run10_va_despues_de_run2_no_antes():
    """Alfabeticamente, run10 < run2. Con n>=10 el replay seguiria otro orden."""
    claves = ["c_run1", "c_run10", "c_run2"]

    assert sorted(claves, key=_orden_de_corrida) == ["c_run1", "c_run2", "c_run10"]


def test_reset_vuelve_a_empezar(fake_baseline):
    entrada = ENTRADA_HAPPY
    primera = pedir(fake_baseline, entrada).data
    pedir(fake_baseline, entrada)

    fake_baseline.reset()

    assert pedir(fake_baseline, entrada).data == primera


def test_sin_clave_input_cae_al_payload_canonico():
    fake = FakeLlm({'{"a": 1}': [{"output": {"ok": True}, "meta": {}}]})

    r = fake.complete_json(LlmRequest(system_prompt="sp", payload={"a": 1}))

    assert r.data == {"ok": True}

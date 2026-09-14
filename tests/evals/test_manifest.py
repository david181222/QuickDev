"""El manifiesto de corrida: lo que hace comparables dos mediciones."""

import json

from quickdev.observability.manifest import RunManifest, git_sha
from quickdev.ports.llm import LlmResponse


def respuesta(**kw) -> LlmResponse:
    base = {"data": {}, "raw_text": "{}", "latency_s": 2.0, "model": "m"}
    base.update(kw)
    return LlmResponse(**base)


def manifiesto() -> RunManifest:
    return RunManifest(
        prompt_version="after",
        rules_version="after",
        schema_version="v1.1",
        model="gemini-2.5-flash",
        n_corridas=10,
        git_sha="abc1234",
    )


# ---------------------------------------------------------------------------
# El estampado
# ---------------------------------------------------------------------------


def test_lleva_las_cinco_versiones():
    """Sin estas cinco, comparar baseline con after es un acto de fe."""
    v = manifiesto().to_dict()["versiones"]

    assert set(v) == {
        "prompt_version",
        "rules_version",
        "schema_version",
        "model",
        "git_sha",
    }


def test_el_git_sha_avisa_si_el_arbol_esta_sucio():
    """Una medicion tomada sobre codigo sin commitear no se puede reproducir."""
    sha = git_sha()

    assert sha, "siempre hay valor, aunque sea 'desconocido'"
    assert " " not in sha, "va dentro de un JSON y de una tabla markdown"
    if sha != "desconocido":
        limpio = sha.removesuffix("-sucio")
        assert limpio.isalnum() and 6 <= len(limpio) <= 40


def test_sin_git_no_revienta(tmp_path):
    """Un manifiesto incompleto es mejor que una corrida sin manifiesto."""
    assert git_sha(raiz=tmp_path) == "desconocido"


# ---------------------------------------------------------------------------
# Los agregados
# ---------------------------------------------------------------------------


def test_cuenta_llamadas_e_intentos():
    m = manifiesto()

    m.record_call(respuesta(attempts=2))
    m.record_call(respuesta())

    d = m.to_dict()["llamadas"]
    assert d["total"] == 2
    assert d["intentos_totales"] == 3


def test_las_llamadas_cacheadas_no_cuentan_como_latencia_del_modelo():
    """Mezclarlas haria que subir n pareciera acelerar el modelo."""
    m = manifiesto()

    m.record_call(respuesta(latency_s=4.0))
    m.record_call(respuesta(latency_s=9.9, from_cache=True))

    assert m.latencia_total_s == 4.0
    assert m.latencia_media_s == 4.0
    assert m.to_dict()["llamadas"]["desde_cache"] == 1
    assert m.tasa_de_cache == 0.5


def test_agrega_los_tokens():
    m = manifiesto()

    m.record_call(respuesta(usage={"total_token_count": 100, "prompt_token_count": 80}))
    m.record_call(respuesta(usage={"total_token_count": 50, "prompt_token_count": 40}))

    assert m.to_dict()["tokens"] == {"prompt_token_count": 120, "total_token_count": 150}


def test_registra_los_errores_con_su_motivo():
    m = manifiesto()

    m.record_error(RuntimeError("se cayo la API"))

    d = m.to_dict()
    assert d["llamadas"]["errores"] == 1
    assert "RuntimeError: se cayo la API" in d["notas"]["errores"][0]


def test_sin_llamadas_no_divide_por_cero():
    d = manifiesto().finish().to_dict()

    assert d["latencia"]["media_s"] == 0.0
    assert d["llamadas"]["total"] == 0


# ---------------------------------------------------------------------------
# El archivo
# ---------------------------------------------------------------------------


def test_escribe_un_json_legible(tmp_path):
    m = manifiesto()
    m.record_call(respuesta())

    archivo = m.finish().write(tmp_path / "corrida")

    guardado = json.loads(archivo.read_text(encoding="utf-8"))
    assert archivo.name == "manifiesto.json"
    assert guardado["versiones"]["prompt_version"] == "after"
    assert guardado["finished_at"], "una corrida cerrada dice cuando termino"

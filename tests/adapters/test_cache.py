"""La cache en disco. El test que importa es que el segundo llamado no toca el envuelto."""

import json

import pytest

from quickdev.adapters.cache import CachingLlm
from quickdev.domain.models import FeedbackReport
from quickdev.ports.llm import LlmRequest

from .dobles import REPORTE_VALIDO, ContadorLlm


@pytest.fixture
def cache(tmp_path):
    def _cache(inner, **kw):
        kw.setdefault("model", "modelo-de-prueba")
        return CachingLlm(inner, cache_dir=tmp_path / "cache", **kw)

    return _cache


# ---------------------------------------------------------------------------
# Lo esencial
# ---------------------------------------------------------------------------


def test_el_segundo_llamado_no_toca_el_envuelto(cache, peticion):
    inner = ContadorLlm()
    c = cache(inner)

    primera = c.complete_json(peticion)
    segunda = c.complete_json(peticion)

    assert inner.llamadas == 1
    assert segunda.data == primera.data == REPORTE_VALIDO


def test_la_respuesta_cacheada_se_marca_como_tal(cache, peticion):
    """`from_cache` es lo que impide que el manifiesto cuente una lectura de
    disco como si fuera latencia del modelo."""
    c = cache(ContadorLlm())

    assert c.complete_json(peticion).from_cache is False
    assert c.complete_json(peticion).from_cache is True


def test_conserva_la_latencia_medida_la_primera_vez(cache, peticion):
    """El coste real de haber producido ese dato no se pierde al cachearlo."""
    c = cache(ContadorLlm())
    c.complete_json(peticion)

    assert c.complete_json(peticion).latency_s == 1.5


def test_dos_instancias_comparten_el_disco(cache, peticion):
    """La cache sobrevive al proceso: es lo que hace barato repetir una corrida."""
    inner = ContadorLlm()
    cache(inner).complete_json(peticion)
    cache(inner).complete_json(peticion)

    assert inner.llamadas == 1


# ---------------------------------------------------------------------------
# La clave
# ---------------------------------------------------------------------------


def test_el_orden_de_las_claves_del_payload_no_cambia_la_clave(cache):
    c = cache(ContadorLlm())
    a = LlmRequest(system_prompt="sp", payload={"a": 1, "b": 2})
    b = LlmRequest(system_prompt="sp", payload={"b": 2, "a": 1})

    assert c.key(a) == c.key(b)


@pytest.mark.parametrize(
    "cambio",
    [
        {"system_prompt": "otro prompt"},
        {"payload": {"input": "otro lote"}},
        {"temperature": 0.7},
        {"max_output_tokens": 1024},
        {"response_schema": FeedbackReport},
    ],
)
def test_cualquier_cosa_que_cambie_la_respuesta_cambia_la_clave(cache, peticion, cambio):
    c = cache(ContadorLlm())
    otra = LlmRequest(
        **{
            "system_prompt": peticion.system_prompt,
            "payload": peticion.payload,
            "temperature": peticion.temperature,
            "max_output_tokens": peticion.max_output_tokens,
            **cambio,
        }
    )

    assert c.key(peticion) != c.key(otra)


def test_dos_modelos_no_comparten_respuestas(cache, peticion):
    """Cachear por peticion sin el modelo haria que cambiar de modelo no cambiara nada."""
    inner = ContadorLlm()
    cache(inner, model="gemini-2.5-flash").complete_json(peticion)
    cache(inner, model="gemini-2.5-pro").complete_json(peticion)

    assert inner.llamadas == 2


# ---------------------------------------------------------------------------
# Robustez
# ---------------------------------------------------------------------------


def test_desactivada_es_transparente(cache, peticion):
    inner = ContadorLlm()
    c = cache(inner, enabled=False)

    c.complete_json(peticion)
    c.complete_json(peticion)

    assert inner.llamadas == 2
    assert list(c.cache_dir.glob("**/*.json")) == []


def test_una_entrada_corrupta_no_tumba_la_corrida(cache, peticion):
    """Un cache es un cache, no una fuente de verdad: si esta roto, se vuelve a pedir."""
    inner = ContadorLlm()
    c = cache(inner)
    c.complete_json(peticion)

    archivo = c.ruta_de(peticion)
    archivo.write_text("esto no es json", encoding="utf-8")

    r = c.complete_json(peticion)

    assert inner.llamadas == 2
    assert r.data == REPORTE_VALIDO


def test_un_error_no_se_cachea(cache, peticion):
    """Solo se guardan respuestas. Un fallo guardado se repetiria para siempre."""
    inner = ContadorLlm([RuntimeError("boom")])
    c = cache(inner)

    with pytest.raises(RuntimeError):
        c.complete_json(peticion)

    assert not c.ruta_de(peticion).exists()


def test_el_archivo_guardado_es_legible_por_una_persona(cache, peticion):
    """Un artefacto de trazabilidad que solo lee la maquina no sirve para auditar."""
    c = cache(ContadorLlm())
    c.complete_json(peticion)

    guardado = json.loads(c.ruta_de(peticion).read_text(encoding="utf-8"))

    assert guardado["respuesta"]["data"] == REPORTE_VALIDO
    assert guardado["respuesta"]["model"] == "doble"

"""Medir es muestrear: una corrida en vivo no puede salir de la cache.

La clave de `CachingLlm` no incluye el numero de corrida, y `correr_eval` manda
la MISMA peticion n veces. Con la cache encendida, la corrida 1 llamaba al modelo
y las demas se servian del disco: n=3 pedidas, 1 muestra real. Todo eval salia
0/n o n/n y la pregunta sobre inestabilidad no podia dispararse nunca. Ver
ADR-0012.

El doble ocupa el sitio de `GeminiAdapter` DENTRO de la composicion real de
`build_llm` (`CachingLlm(RetryingLlm(...))`), con una cache en `tmp_path`: se
prueba el cableado de verdad, no una composicion hecha a mano para el test.
"""

import json

import pytest

from evals.cases import EVALS
from evals.runner import construir_corrida, correr_eval
from quickdev.adapters import build_llm
from quickdev.config import Settings
from quickdev.ports.llm import LlmRequest, LlmResponse

REPORTE = {
    "resumen_general": "Respuesta del doble.",
    "sentimiento_general": "neutro",
    "version_juego": None,
    "total_comentarios_analizados": 0,
    "requiere_revision_humana": True,
    "problemas_detectados": [],
    "comentarios_evidencia": [],
    "comentarios_descartados": [],
}


class ModeloQueCuenta:
    """Un `LlmPort` que cuenta cuantas peticiones le llegan de verdad al modelo."""

    def __init__(self) -> None:
        self.llamadas = 0

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self.llamadas += 1
        return LlmResponse(data=REPORTE, raw_text=json.dumps(REPORTE), model="doble")


@pytest.fixture
def modelo(monkeypatch) -> ModeloQueCuenta:
    """Sustituye a Gemini en `build_llm`, sin tocar la cache ni los reintentos."""
    doble = ModeloQueCuenta()
    monkeypatch.setattr(
        "quickdev.adapters.GeminiAdapter", lambda client=None, settings=None: doble
    )
    return doble


def settings_con_cache(tmp_path) -> Settings:
    """La cache ENCENDIDA, como la trae el producto por defecto."""
    return Settings(
        prompt_version="after",
        rules_version="after",
        gemini_api_key="",
        cache_dir=tmp_path / "cache",
        cache_enabled=True,
    )


def test_una_corrida_en_vivo_con_n3_llama_al_modelo_3_veces(modelo, tmp_path):
    corrida = construir_corrida(prompt_version="after", n=3, settings=settings_con_cache(tmp_path))

    filas = correr_eval(EVALS[0], corrida)

    assert modelo.llamadas == 3
    assert corrida.manifest.llamadas_cacheadas == 0
    assert [f["from_cache"] for f in filas] == [False, False, False]


def test_una_corrida_en_vivo_no_reutiliza_lo_que_dejo_otra(modelo, tmp_path):
    """Dos mediciones seguidas son dos muestras, no una muestra leida dos veces."""
    for _ in range(2):
        corrida = construir_corrida(
            prompt_version="after", n=3, settings=settings_con_cache(tmp_path)
        )
        correr_eval(EVALS[0], corrida)

    assert modelo.llamadas == 6


def test_el_producto_sigue_usando_la_cache(modelo, tmp_path):
    """La cache es para `quickdev analyze`: no volver a pagar la misma respuesta."""
    llm = build_llm(settings_con_cache(tmp_path))
    peticion = LlmRequest(system_prompt="sp", payload={"input": "lote"})

    llm.complete_json(peticion)
    segunda = llm.complete_json(peticion)

    assert modelo.llamadas == 1
    assert segunda.from_cache is True

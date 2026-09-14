"""Los adaptadores: las implementaciones concretas de los puertos.

El unico lugar del repo autorizado a importar `google.genai`, y solo en
`gemini.py`. El resto son decoradores del mismo puerto y no saben que proveedor
hay debajo.

La composicion se lee de fuera hacia dentro:

    CachingLlm(RetryingLlm(GeminiAdapter()))   # produccion
    FakeLlm.from_crudo(...)                    # tests y CI

Ese orden no es arbitrario. La cache va FUERA del reintento para que una
respuesta ya cacheada no pase siquiera por la politica de reintentos: si la
tienes, no hay nada que reintentar. Al reves, cada acierto de cache atravesaria
el decorador de reintentos sin razon, y un fallo guardado se reintentaria
eternamente.
"""

from quickdev.adapters.cache import CachingLlm
from quickdev.adapters.fake import FakeLlm, SinRespuestaGrabada
from quickdev.adapters.gemini import GeminiAdapter
from quickdev.adapters.retry import RetryingLlm
from quickdev.config import Settings
from quickdev.ports.llm import LlmPort

__all__ = [
    "CachingLlm",
    "FakeLlm",
    "GeminiAdapter",
    "RetryingLlm",
    "SinRespuestaGrabada",
    "build_llm",
]


def build_llm(settings: Settings | None = None, client: object | None = None) -> LlmPort:
    """La composicion de produccion, en un solo sitio.

    Tenerla aqui y no repartida por los llamadores es lo que evita que dentro de
    dos meses haya una corrida de evals sin cache y otra con reintentos
    distintos, y que nadie sepa cual produjo que numero.
    """
    settings = settings or Settings()
    return CachingLlm(
        RetryingLlm(
            GeminiAdapter(client=client, settings=settings),
            retries=settings.retries,
            backoff_base_s=settings.backoff_base_s,
        ),
        cache_dir=settings.cache_dir,
        model=settings.model,
        enabled=settings.cache_enabled,
    )

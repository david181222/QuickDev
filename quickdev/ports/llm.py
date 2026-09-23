"""El puerto del modelo de lenguaje.

Responsabilidad: definir como el dominio pide una respuesta JSON a un modelo, sin
saber que modelo es ni quien lo sirve.

Lo que NO le corresponde: importar ningun SDK. El unico archivo del repo que
importa `google.genai` es `adapters/gemini.py`.

Nota de diseno: `complete_json` devuelve un `dict`, no un `FeedbackReport`. El
parseo al modelo de dominio ocurre en la capa de aplicacion. Esa eleccion es
deliberada y tiene dos consecuencias buenas: los adaptadores no dependen del
dominio (asi se pueden escribir en paralelo), y el JSON crudo del modelo se
conserva intacto para los evals, que necesitan evaluar las aserciones contra el
crudo y contra el corregido por separado.
"""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


@dataclass(frozen=True)
class LlmRequest:
    """Una peticion al modelo.

    `response_schema` es el modelo Pydantic que el proveedor debe hacer cumplir.
    Cuando viene informado, la forma de la respuesta la garantiza el proveedor en
    vez de pedirse por prompt, y desaparece una clase entera de fallos:
    JSONDecodeError, campos extra, campos faltantes, enums invalidos. Ver
    ADR-0009.
    """

    system_prompt: str
    payload: dict
    response_schema: type[BaseModel] | None = None
    max_output_tokens: int = 6144
    temperature: float = 0.0


@dataclass(frozen=True)
class LlmResponse:
    """La respuesta del modelo, mas lo que hizo falta para conseguirla.

    Los metadatos no son decoracion: son lo que permite responder con dato la
    pregunta de diagnostico "la tool devolvio mal?". `attempts` esta separado de
    cualquier nocion de fallo a proposito: reintentar no es fallar, y la
    implementacion vieja (`evals/motor.py:374`) los confundia, lo que hacia que
    un happy path de 3/3 apareciera reportado como fallo de la tool por un rate
    limit transitorio.
    """

    data: dict
    raw_text: str
    attempts: int = 1
    truncated: bool = False
    latency_s: float = 0.0
    from_cache: bool = False
    model: str = ""
    usage: dict = field(default_factory=dict)


class LlmPort(Protocol):
    """Lo unico que el dominio sabe sobre un modelo de lenguaje.

    Implementaciones previstas:
      - `adapters/gemini.py`  el proveedor real
      - `adapters/fake.py`    reproduce outputs guardados; CI sin red ni cuota
      - `adapters/retry.py`   decorador de reintentos
      - `adapters/cache.py`   decorador de cache en disco

    Los decoradores tambien implementan este puerto, asi que se componen:
        CachingLlm(RetryingLlm(GeminiAdapter()))
    """

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        """Pide una respuesta JSON al modelo.

        Raises:
            LlmTerminalError: el error no tiene sentido reintentarlo.
            LlmRetryableError: el error es transitorio.
        """
        ...


class LlmError(RuntimeError):
    """Cualquier fallo de la capa de llamada al modelo."""


class LlmRetryableError(LlmError):
    """Transitorio: 429, 5xx, timeouts. Tiene sentido reintentar con backoff."""


class LlmTerminalError(LlmError):
    """Definitivo: 400, 401, esquema rechazado. Reintentar solo pierde tiempo.

    Esta distincion existe porque `evals/motor.py:383-389` trataba cualquier
    excepcion como reintentable y dormia 45*(intento+1) segundos: con una API key
    invalida, el eval se quedaba 135 segundos dormido antes de rendirse.
    """

"""El adaptador real: Gemini.

Responsabilidad: traducir un `LlmRequest` a una llamada del SDK de Google y la
respuesta de vuelta a un `LlmResponse`. Y traducir los errores del proveedor a la
jerarquia del puerto.

Lo que NO le corresponde: reintentar (`retry.py`), cachear (`cache.py`), saber
que es un `FeedbackReport` (el parseo al dominio ocurre en la capa de
aplicacion), ni leer el `.env` por su cuenta.

Este es el UNICO archivo del repo que importa `google.genai`. La comprobacion es
un grep, y esta en la descripcion del PR:

    grep -rn "genai" quickdev/ | grep -v adapters/gemini.py   # no devuelve nada

## Sin singleton

`evals/motor.py:213-224` tenia `get_client()` con `global _client`: estado
oculto, mutable y compartido por todo el proceso. No habia forma de correr dos
configuraciones en el mismo test, ni de sustituir el cliente sin parchear el
modulo. Aqui el cliente se recibe en `__init__` o se construye ahi mismo, y el
adaptador no guarda nada mas.

## Quien clasifica los errores

Los clasifica ESTE modulo, no `retry.py`. Es el unico que sabe que significa un
`ClientError` de Google; el decorador de reintentos solo tiene que saber si lo
que le llego se puede reintentar o no. Si la clasificacion viviera en el
decorador, cambiar de proveedor obligaria a tocar la politica de reintentos, que
no tiene nada que ver con el proveedor. Ver ADR-0006.
"""

import json
import re
import time

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from quickdev.config import Settings
from quickdev.ports.llm import (
    LlmRequest,
    LlmResponse,
    LlmRetryableError,
    LlmTerminalError,
)

# Un 429 es cuota agotada por ahora; un 408 es un timeout del lado del servidor.
# Los dos se reintentan. El resto de los 4xx son culpa de la peticion, y
# reintentarlos solo gasta tiempo: eso es exactamente lo que hacia el codigo
# viejo, que dormia 45*(intento+1) segundos ante una API key invalida.
CODIGOS_REINTENTABLES = frozenset({408, 409, 429})

# El SDK ya devuelve JSON cuando se le pide response_mime_type, pero el modelo
# puede envolverlo en una valla de markdown. Se quita antes de parsear.
_VALLA_MARKDOWN = re.compile(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$")


class GeminiAdapter:
    """Implementa `LlmPort` contra la API de Gemini."""

    def __init__(
        self,
        client: genai.Client | None = None,
        settings: Settings | None = None,
    ) -> None:
        """
        Args:
            client: un cliente ya construido. Se inyecta en los tests y en
                cualquier sitio que quiera controlar el transporte.
            settings: de donde salen la api key y el modelo. Si no se pasa, se
                construye uno, que lee el `.env` de la raiz.

        Raises:
            LlmTerminalError: no hay API key. Falla al construir, no a mitad de
                una corrida de evals que ya gasto llamadas.
        """
        self.settings = settings or Settings()
        self.model = self.settings.model
        if client is not None:
            self.client = client
            return
        if not self.settings.gemini_api_key:
            raise LlmTerminalError(
                "Falta GEMINI_API_KEY en el .env de la raiz. Para correr sin "
                "clave usa FakeLlm (adapters/fake.py), que reproduce los "
                "outputs ya guardados en evals/resultados/."
            )
        self.client = genai.Client(api_key=self.settings.gemini_api_key)

    # -----------------------------------------------------------------------

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        """Una llamada, un intento. Los reintentos son de `RetryingLlm`."""
        inicio = time.perf_counter()
        try:
            respuesta = self.client.models.generate_content(
                model=self.model,
                contents=json.dumps(request.payload, ensure_ascii=False),
                config=self._config(request),
            )
        except Exception as exc:
            raise _clasificar(exc) from exc

        latencia = time.perf_counter() - inicio
        truncado = self._truncado(respuesta)
        texto = _VALLA_MARKDOWN.sub("", (respuesta.text or "").strip())

        try:
            datos = json.loads(texto)
        except json.JSONDecodeError as exc:
            raise self._error_de_parseo(exc, truncado, texto) from exc

        if not isinstance(datos, dict):
            raise LlmTerminalError(
                f"El modelo devolvio un {type(datos).__name__} en la raiz, no un "
                f"objeto JSON. El contrato es un objeto."
            )

        return LlmResponse(
            data=datos,
            raw_text=texto,
            attempts=1,
            truncated=truncado,
            latency_s=latencia,
            model=self.model,
            usage=self._usage(respuesta),
        )

    # -- detalles ------------------------------------------------------------

    def _config(self, request: LlmRequest) -> types.GenerateContentConfig:
        """La forma la hace cumplir el proveedor, no una frase del prompt.

        Cuando `response_schema` viene informado, el proveedor garantiza la
        estructura y desaparece una clase entera de fallos: JSONDecodeError,
        campos faltantes, enums invalidos. Ver ADR-0009. El esquema no se pasa
        tal cual: ver `_esquema_para_el_proveedor` y ADR-0014.
        """
        return types.GenerateContentConfig(
            system_instruction=request.system_prompt,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            response_mime_type="application/json",
            response_schema=_esquema_para_el_proveedor(request.response_schema),
        )

    @staticmethod
    def _truncado(respuesta: object) -> bool:
        """True si el modelo se quedo sin tokens a mitad de la respuesta."""
        try:
            return "MAX_TOKENS" in str(respuesta.candidates[0].finish_reason)
        except (AttributeError, IndexError, TypeError):
            return False

    @staticmethod
    def _usage(respuesta: object) -> dict:
        """Tokens de la llamada, si el proveedor los informa."""
        uso = getattr(respuesta, "usage_metadata", None)
        if uso is None:
            return {}
        campos = (
            "prompt_token_count",
            "candidates_token_count",
            "thoughts_token_count",
            "total_token_count",
        )
        return {c: getattr(uso, c) for c in campos if isinstance(getattr(uso, c, None), int)}

    @staticmethod
    def _error_de_parseo(
        exc: json.JSONDecodeError, truncado: bool, texto: str
    ) -> LlmTerminalError | LlmRetryableError:
        """Un JSON roto por truncamiento no se arregla reintentando.

        Con `temperature=0` y el mismo input, el segundo intento produce la misma
        respuesta y se corta en el mismo sitio: reintentar es gastar cuota para
        obtener el mismo fallo. Lo que hay que subir es `max_output_tokens`. Un
        JSON roto SIN truncamiento si puede ser transitorio, y se reintenta.
        """
        muestra = texto[:200]
        if truncado:
            return LlmTerminalError(
                f"Respuesta truncada por max_output_tokens y JSON incompleto: {exc}. "
                f"Reintentar con temperature=0 da el mismo corte; sube "
                f"max_output_tokens. Muestra: {muestra!r}"
            )
        return LlmRetryableError(f"JSON invalido del modelo: {exc}. Muestra: {muestra!r}")


def _esquema_para_el_proveedor(modelo: type[BaseModel] | None) -> dict | None:
    """El JSON Schema del modelo, sin `additionalProperties`.

    `response_schema` acepta un subconjunto de OpenAPI 3.0 que no incluye
    `additionalProperties`, y el `extra="forbid"` de los modelos del dominio lo
    genera en cada objeto. Pasar el modelo Pydantic tal cual producia un 400 en
    el 100% de las llamadas ("Unknown name additional_properties at
    'generation_config.response_schema'"), y ningun test lo vio porque el
    cliente doble no valida el esquema. Ver ADR-0014.

    El SDK trata un modelo Pydantic y un dict por el mismo camino
    (`model_json_schema()` y despues `process_schema`), asi que la unica
    diferencia en la peticion es ese campo. No se pierde la garantia: un campo
    extra en la respuesta sigue siendo un error de parseo en `AnalyzeBatch`,
    porque el dominio conserva `extra="forbid"`.
    """
    if modelo is None:
        return None
    return _sin_additional_properties(modelo.model_json_schema())


def _sin_additional_properties(nodo: object) -> object:
    if isinstance(nodo, dict):
        return {
            clave: _sin_additional_properties(valor)
            for clave, valor in nodo.items()
            if clave != "additionalProperties"
        }
    if isinstance(nodo, list):
        return [_sin_additional_properties(valor) for valor in nodo]
    return nodo


def _clasificar(exc: Exception) -> LlmRetryableError | LlmTerminalError:
    """Traduce una excepcion del proveedor a la jerarquia del puerto.

    Todo lo que no se reconoce se trata como TERMINAL. Es deliberado, y es al
    reves de lo que hacia `evals/motor.py:383-389`, que trataba cualquier
    excepcion como reintentable: un error desconocido tiene mas probabilidad de
    ser un bug nuestro que un fallo transitorio de la red, y dormir tres veces
    antes de mostrarlo solo retrasa el diagnostico.
    """
    if isinstance(exc, genai_errors.ServerError):
        return LlmRetryableError(f"5xx del proveedor: {_mensaje(exc)}")

    if isinstance(exc, genai_errors.ClientError):
        codigo = getattr(exc, "code", None)
        if codigo in CODIGOS_REINTENTABLES:
            return LlmRetryableError(f"{codigo} del proveedor: {_mensaje(exc)}")
        return LlmTerminalError(f"{codigo} del proveedor: {_mensaje(exc)}")

    if isinstance(exc, TimeoutError | ConnectionError):
        return LlmRetryableError(f"fallo de red: {_mensaje(exc)}")

    # httpx no es una dependencia declarada nuestra: viene con el SDK. Se
    # reconoce por nombre de modulo para no importarlo y no atarnos a su version.
    if type(exc).__module__.split(".")[0] == "httpx":
        return LlmRetryableError(f"fallo de transporte: {type(exc).__name__}: {_mensaje(exc)}")

    return LlmTerminalError(f"{type(exc).__name__}: {_mensaje(exc)}")


def _mensaje(exc: Exception) -> str:
    return str(getattr(exc, "message", None) or exc)[:300]

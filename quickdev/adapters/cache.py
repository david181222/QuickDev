"""Cache en disco, como decorador.

Responsabilidad: no volver a pagar por una respuesta que ya tenemos.

Lo que NO le corresponde: decidir si la cache esta encendida (eso es
`Settings.cache_enabled`), ni saber que proveedor hay debajo.

## Para que sirve de verdad

Para el producto: `quickdev analyze` sobre un lote que ya se analizo con el
mismo prompt, modelo y configuracion no vuelve a pagar la llamada.

## Para que NO sirve: medir

Este docstring decia que la cache "hace asequible subir n" en los evals. Era
falso: lo anula. La clave no lleva el numero de corrida y `correr_eval` manda la
MISMA peticion n veces, asi que con la cache encendida la corrida 1 llama al
modelo y las otras n-1 salen del disco. n pedidas, una muestra. Por eso las
corridas en vivo de `evals/runner.py` la apagan. Ver ADR-0012.

## Por que la clave incluye la temperatura

Porque con temperatura alta dos llamadas identicas deben poder dar resultados
distintos, y cachearlas las convertiria en la misma en silencio. Al incluir la
temperatura en la clave, una corrida a 0.7 no reutiliza la de 0.0. Ni siquiera
`temperature=0` garantiza "misma entrada, misma salida": el baseline midio
`hitl_marcado` en 1/3 y 2/3 con temperatura 0. Esa varianza es justo lo que una
medicion tiene que ver, y la razon de que medir no pase por aqui.

## Que NO invalida la cache

Nada la invalida sola: un archivo cacheado sobrevive a un cambio de prompt solo
si el prompt entra en la clave, y entra. Lo que no entra es el codigo del
adaptador. Si cambia como se parsea la respuesta, hay que borrar `.cache/` a
mano. Esta anotado aqui porque es la clase de cosa que hace perder una tarde.
"""

import hashlib
import json
from dataclasses import replace
from pathlib import Path

from quickdev.ports.llm import LlmPort, LlmRequest, LlmResponse

VERSION_DE_CACHE = "v1"


class CachingLlm:
    """Envuelve otro `LlmPort` y guarda sus respuestas en disco."""

    def __init__(
        self,
        inner: LlmPort,
        cache_dir: Path,
        model: str = "",
        enabled: bool = True,
    ) -> None:
        """
        Args:
            inner: el puerto que se envuelve.
            cache_dir: raiz de la cache. Se crea si no existe.
            model: entra en la clave. Dos modelos distintos no comparten
                respuestas aunque la peticion sea identica; el `LlmRequest` no
                lleva el modelo, asi que se recibe aqui.
            enabled: con False, el decorador es transparente. Existe para no
                tener que cambiar la composicion cuando se quiere medir de
                verdad contra la API.
        """
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.enabled = enabled

    # -----------------------------------------------------------------------

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        """Devuelve la respuesta guardada si existe; si no, llama y la guarda."""
        if not self.enabled:
            return self.inner.complete_json(request)

        archivo = self.ruta_de(request)
        guardada = self._leer(archivo)
        if guardada is not None:
            return guardada

        respuesta = self.inner.complete_json(request)
        self._escribir(archivo, respuesta)
        return respuesta

    # -- clave y disco -------------------------------------------------------

    def key(self, request: LlmRequest) -> str:
        """El hash de todo lo que puede cambiar la respuesta.

        El payload se serializa con `sort_keys` para que dos dicts iguales con
        las claves en otro orden den la misma clave.
        """
        material = json.dumps(
            {
                "v": VERSION_DE_CACHE,
                "model": self.model,
                "system_prompt": request.system_prompt,
                "payload": request.payload,
                "temperature": request.temperature,
                "max_output_tokens": request.max_output_tokens,
                "schema": getattr(request.response_schema, "__name__", None),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def ruta_de(self, request: LlmRequest) -> Path:
        """Donde vive esa entrada. Un subdirectorio por modelo, para poder borrar por modelo."""
        subdir = self.model.replace("/", "_") or "sin-modelo"
        return self.cache_dir / subdir / f"{self.key(request)}.json"

    def _leer(self, archivo: Path) -> LlmResponse | None:
        """La entrada guardada, o None si no existe o esta corrupta.

        Una entrada ilegible se ignora y se vuelve a pedir. Una cache corrupta
        no debe tumbar una corrida: es un cache, no una fuente de verdad.
        """
        if not archivo.exists():
            return None
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
            respuesta = LlmResponse(**datos["respuesta"])
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            return None
        # `latency_s` se conserva tal como se midio la primera vez: es el coste
        # real de haber producido ese dato. `from_cache` es lo que avisa de que
        # esta llamada no lo pago, y es lo que mira el manifiesto para no
        # mezclar latencias reales con lecturas de disco.
        return replace(respuesta, from_cache=True)

    def _escribir(self, archivo: Path, respuesta: LlmResponse) -> None:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        contenido = {
            "respuesta": {
                "data": respuesta.data,
                "raw_text": respuesta.raw_text,
                "attempts": respuesta.attempts,
                "truncated": respuesta.truncated,
                "latency_s": respuesta.latency_s,
                "model": respuesta.model,
                "usage": respuesta.usage,
            }
        }
        archivo.write_text(
            json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
        )

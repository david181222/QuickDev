"""Reintentos, como decorador.

Responsabilidad: decidir cuantas veces se reintenta y cuanto se espera entre
intentos. Nada mas.

Lo que NO le corresponde: saber que proveedor hay debajo ni interpretar codigos
HTTP. Eso lo hace `adapters/gemini.py`, que es el unico que conoce el SDK; aqui
solo se mira si lo que subio fue un `LlmRetryableError` o un `LlmTerminalError`.

## Por que decorador y no un parametro del cliente

Porque reintentar no es asunto del proveedor. Envolviendo se compone:

    CachingLlm(RetryingLlm(GeminiAdapter()))   # produccion
    RetryingLlm(FakeLlm.from_crudo(...))       # tests de la politica

y cada pieza se prueba sola. Con `retries=3` dentro del cliente, probar la
politica de reintentos exige un cliente, y probar el cliente arrastra la
politica. Ver ADR-0006.

## Dos defectos concretos del codigo viejo que esto arregla

1. `evals/motor.py:383-389` dormia `45*(intento+1)` segundos ante CUALQUIER
   excepcion. Con una API key invalida el eval se quedaba 135 segundos dormido
   antes de rendirse, para un error que no iba a cambiar. Aqui un
   `LlmTerminalError` se propaga inmediatamente, sin dormir.
2. `evals/motor.py:374` ponia `tool_ok=False` si hubo cualquier reintento,
   aunque el segundo intento saliera perfecto. Por eso el diagnostico del
   baseline respondia "la tool devolvio mal? SI" en un happy path de 3/3 que
   solo habia tropezado con un rate limit. Aqui `attempts` viaja en la respuesta
   y no significa fallo: reintentar no es fallar.
"""

import time
from collections.abc import Callable
from dataclasses import replace

from quickdev.ports.llm import (
    LlmPort,
    LlmRequest,
    LlmResponse,
    LlmRetryableError,
)


class RetryingLlm:
    """Envuelve otro `LlmPort` y reintenta lo que es transitorio."""

    def __init__(
        self,
        inner: LlmPort,
        retries: int = 3,
        backoff_base_s: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """
        Args:
            inner: el puerto que se envuelve.
            retries: numero TOTAL de intentos, no de reintentos extra. Con 3 se
                llama como mucho tres veces.
            backoff_base_s: espera del primer reintento. Crece al doble en cada
                uno: 5, 10, 20. El viejo era lineal y empezaba en 45.
            sleep: se inyecta para que los tests no duerman de verdad. Sin esto,
                probar el backoff cuesta 15 segundos por test.
        """
        if retries < 1:
            raise ValueError("retries es el numero total de intentos: minimo 1.")
        self.inner = inner
        self.retries = retries
        self.backoff_base_s = backoff_base_s
        self._sleep = sleep

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        """Llama al puerto envuelto, reintentando solo lo reintentable.

        Raises:
            LlmTerminalError: propagado tal cual y de inmediato.
            LlmRetryableError: el ultimo, cuando se agotaron los intentos.
        """
        ultimo: LlmRetryableError | None = None

        for intento in range(1, self.retries + 1):
            try:
                respuesta = self.inner.complete_json(request)
            except LlmRetryableError as exc:
                ultimo = exc
                if intento == self.retries:
                    break
                self._sleep(self.backoff_base_s * (2 ** (intento - 1)))
                continue

            # Exito. Se anota en que intento salio: es un dato del diagnostico,
            # no una marca de fallo.
            return _con_intentos(respuesta, intento)

        raise LlmRetryableError(
            f"Agotados los {self.retries} intentos. Ultimo error: {ultimo}"
        ) from ultimo


def _con_intentos(respuesta: LlmResponse, intentos: int) -> LlmResponse:
    """Una copia de la respuesta con el numero de intento en que salio.

    `LlmResponse` es frozen a proposito, asi que se reemplaza en vez de mutarse.
    Si el envuelto ya reporto mas intentos que nosotros (porque tambien es un
    decorador), se conserva el mayor.
    """
    if respuesta.attempts >= intentos:
        return respuesta
    return replace(respuesta, attempts=intentos)

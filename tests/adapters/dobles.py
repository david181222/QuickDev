"""Dobles compartidos por los tests de adaptadores.

Ninguno de estos tests toca la red. El criterio de aceptacion de la rama es
literal: desconecta el wifi y `pytest -m "not llm"` sigue verde.

Los dobles estan aqui y las fixtures en `conftest.py`, como es habitual. Lo que
no es habitual es que esta carpeta sea un paquete: el porque esta en
`__init__.py`, y tiene que ver con no romper los tests de `core/edwin`.
"""

import json
from dataclasses import dataclass, field

from quickdev.ports.llm import LlmRequest, LlmResponse

REPORTE_VALIDO = {
    "resumen_general": "Reporte de prueba.",
    "sentimiento_general": "negativo",
    "version_juego": "v0.8.2",
    "total_comentarios_analizados": 2,
    "requiere_revision_humana": False,
    "problemas_detectados": [],
    "comentarios_evidencia": [],
    "comentarios_descartados": [],
}


# ---------------------------------------------------------------------------
# Dobles del SDK de Google
# ---------------------------------------------------------------------------


@dataclass
class FakeCandidate:
    finish_reason: str = "STOP"


@dataclass
class FakeUsage:
    prompt_token_count: int = 100
    candidates_token_count: int = 50
    thoughts_token_count: int = 0
    total_token_count: int = 150


@dataclass
class FakeSdkResponse:
    """Lo minimo de `GenerateContentResponse` que usa el adaptador."""

    text: str
    candidates: list = field(default_factory=lambda: [FakeCandidate()])
    usage_metadata: FakeUsage = field(default_factory=FakeUsage)


class FakeModels:
    """Sustituye a `client.models`. Registra las llamadas, y devuelve o lanza."""

    def __init__(self, respuestas: list) -> None:
        self.respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def generate_content(self, *, model, contents, config):
        self.llamadas.append({"model": model, "contents": contents, "config": config})
        if not self.respuestas:
            raise AssertionError("El doble se quedo sin respuestas programadas.")
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


class FakeClient:
    """Sustituye a `genai.Client`. No abre ninguna conexion."""

    def __init__(self, *respuestas) -> None:
        self.models = FakeModels(respuestas)


# ---------------------------------------------------------------------------
# Dobles de nuestro propio puerto
# ---------------------------------------------------------------------------


class ContadorLlm:
    """Un `LlmPort` que cuenta llamadas. Para probar los decoradores."""

    def __init__(self, respuestas=None, data=None) -> None:
        self.data = data or REPORTE_VALIDO
        self.respuestas = list(respuestas) if respuestas is not None else None
        self.llamadas = 0
        self.peticiones: list[LlmRequest] = []

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self.llamadas += 1
        self.peticiones.append(request)
        if self.respuestas is not None:
            siguiente = self.respuestas.pop(0)
            if isinstance(siguiente, Exception):
                raise siguiente
            return siguiente
        return LlmResponse(
            data=self.data,
            raw_text=json.dumps(self.data),
            latency_s=1.5,
            model="doble",
            usage={"total_token_count": 150},
        )


class RelojFalso:
    """Sustituye a `time.sleep`: anota cuanto se habria dormido, sin dormir.

    Sin esto, probar que el backoff crece cuesta 15 segundos de suite por test, y
    una suite lenta acaba sin correrse.
    """

    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)

    @property
    def total(self) -> float:
        return sum(self.esperas)

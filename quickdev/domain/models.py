"""Modelos del dominio de QuickDev.

Responsabilidad: definir la forma de los datos del producto. Nada mas.

Lo que NO le corresponde a este modulo: validar hechos (eso son las reglas de
`domain/rules/`), llamar al modelo (eso es `ports/` + `adapters/`), leer o
escribir archivos.

Sobre los nombres, dos convenciones distintas que conviven a proposito:

- Las CLASES y los alias de tipo estan en ingles, como el resto del codigo.
- Los CAMPOS de `FeedbackReport` y de sus hijos estan en espanol, y no se
  renombran. Son el contrato del producto: el JSON que el modelo devuelve, que
  las reglas verifican y que las mediciones de `evals/resultados/` ya usaron.
  Renombrar `requiere_revision_humana` no es un detalle de estilo, invalida el
  baseline con el que comparamos. Ver ADR-0002.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Version del contrato de salida. Se estampa en cada corrida de evals para que
# una medicion diga contra que forma se produjo.
#
# v1   -> el esquema congelado original (`evals/resultados/baseline` y `after`).
# v1.1 -> identico a v1 mas `evidencia_idx`, un campo nuevo y opcional. El bump
#         es menor porque el cambio es aditivo: un consumidor de v1 sigue
#         leyendo un reporte v1.1 sin enterarse. Ver ADR-0002 y ADR-0005.
SCHEMA_VERSION = "v1.1"


# ---------------------------------------------------------------------------
# Vocabularios cerrados
# ---------------------------------------------------------------------------
# Listas cerradas, no strings libres: es la mitad del trabajo que hace el codigo
# en la frontera "el modelo interpreta, el codigo verifica".

Fuente = Literal["discord", "steam", "encuesta", "red_social"]

Categoria = Literal[
    "balance",
    "bugs",
    "dificultad",
    "rendimiento",
    "interfaz",
    "diversion",
    "economia",
    "otro",
]

Prioridad = Literal["alta", "media", "baja"]

Sentimiento = Literal["positivo", "neutro", "negativo"]

MotivoDescarte = Literal["ruido", "sesgado", "extremista", "sin_relacion"]


# ---------------------------------------------------------------------------
# Entrada
# ---------------------------------------------------------------------------


class PlaytestComment(BaseModel):
    """Un comentario de un playtester, tal como llego."""

    model_config = ConfigDict(frozen=True)

    fuente: Fuente
    texto: str = Field(min_length=1)


class PlaytestBatch(BaseModel):
    """El lote de comentarios de un ciclo de playtest.

    `build` es la version analizada, declarada por quien arma el lote, NO por el
    modelo. `None` significa "build no especificada". Esta distincion es el nucleo
    del edge case que el baseline no resolvia: un jugador puede mencionar otra
    version dentro de su comentario, y esa mencion no es la build analizada.
    """

    model_config = ConfigDict(frozen=True)

    build: str | None = None
    comentarios: list[PlaytestComment] = Field(default_factory=list)

    @property
    def total(self) -> int:
        """El conteo real del lote.

        Esta propiedad es la unica fuente de verdad sobre cuantos comentarios
        hay. `total_comentarios_analizados` del reporte se compara contra ella;
        nunca al contrario.
        """
        return len(self.comentarios)

    def texto_de(self, indice: int) -> str:
        """El texto literal del comentario en esa posicion del lote.

        Existe para que las citas del reporte se resuelvan por indice en vez de
        por coincidencia de texto. Ver ADR-0005.
        """
        return self.comentarios[indice].texto


# ---------------------------------------------------------------------------
# Salida: el contrato congelado
# ---------------------------------------------------------------------------


class DetectedIssue(BaseModel):
    """Un problema agregado detectado en el lote."""

    model_config = ConfigDict(extra="forbid")

    categoria: Categoria
    descripcion: str = Field(max_length=200)
    frecuencia: int = Field(ge=1)
    prioridad: Prioridad
    fuente_predominante: Fuente | None = None

    # Campo nuevo en v1.1, opcional para no romper la comparabilidad con v1.
    # Indices (base 0) de los comentarios del lote que sustentan este problema.
    # Con esto, `frecuencia` deja de ser un numero que el modelo propone y el
    # codigo acota: pasa a ser `len(set(evidencia_idx))`, calculado por codigo.
    evidencia_idx: list[int] = Field(default_factory=list)


class QuotedComment(BaseModel):
    """Una cita de evidencia. `texto` debe existir literalmente en el lote."""

    model_config = ConfigDict(extra="forbid")

    texto: str
    fuente: str | None = None


class DiscardedComment(BaseModel):
    """Un comentario que el modelo decidio no usar, con su motivo.

    Nada desaparece en silencio: todo lo descartado queda aqui para que el
    desarrollador pueda auditar que se ignoro y por que.
    """

    model_config = ConfigDict(extra="forbid")

    texto: str
    motivo: MotivoDescarte


class FeedbackReport(BaseModel):
    """El reporte agregado. El contrato de salida del producto.

    Estos ocho campos y estos ocho nombres son el esquema congelado. `extra` esta
    en "forbid" a proposito: un campo que el esquema no declara es un error de
    parseo en la frontera, no un hallazgo de validacion. Mover esa comprobacion
    a la frontera es lo que permite que el proveedor la garantice via
    `response_schema` en vez de pedirla por prompt. Ver ADR-0009.
    """

    model_config = ConfigDict(extra="forbid")

    # Los ocho son REQUERIDOS, ninguno tiene default. `version_juego` es
    # requerido-pero-nulable: el modelo tiene que pronunciarse, aunque sea con
    # null. Si `comentarios_descartados` pudiera omitirse y volverse [], un lote
    # donde el modelo descarto comentarios se veria igual que uno donde no
    # descarto ninguno, y "nada desaparece en silencio" dejaria de ser cierto.
    # Esto reproduce la comprobacion original `set(output.keys()) ==
    # REQUIRED_FIELDS`, ahora en la frontera de parseo.
    resumen_general: str = Field(max_length=400)
    sentimiento_general: Sentimiento
    version_juego: str | None
    total_comentarios_analizados: int = Field(ge=0)
    requiere_revision_humana: bool
    problemas_detectados: list[DetectedIssue]
    comentarios_evidencia: list[QuotedComment]
    comentarios_descartados: list[DiscardedComment]


# Los nombres del contrato, en un solo lugar. `tests/domain/test_contract.py`
# comprueba que coincidan con los campos reales de `FeedbackReport`, para que
# nadie renombre uno sin que algo se ponga rojo.
CONTRACT_FIELDS: frozenset[str] = frozenset(
    {
        "resumen_general",
        "sentimiento_general",
        "version_juego",
        "total_comentarios_analizados",
        "requiere_revision_humana",
        "problemas_detectados",
        "comentarios_evidencia",
        "comentarios_descartados",
    }
)

"""Utilidades y datos de prueba compartidos.

La disciplina es la misma que ya usaban las regresiones del harness: se parte de
un reporte de referencia CORRECTO y cada test perturba UNA SOLA COSA. Asi, cuando
un test falla, se sabe que la regla atrapo justo eso y no otra cosa.

Nota para quien anada tests en otra carpeta: NO hace falta tocar este archivo.
pytest compone los conftest por directorio, asi que un
`tests/adapters/conftest.py` o `tests/evals/conftest.py` hereda estas fixtures y
puede anadir las suyas sin pisar nada.
"""

import pytest

from quickdev.domain.models import FeedbackReport, PlaytestBatch, PlaytestComment

# Comentarios reales del lote de playtest, en un solo sitio para que las citas
# de los tests sean citas de verdad y no cadenas parecidas.
BUG_PARED = "Hay un bug donde el personaje se queda atascado en la pared del nivel 3."
OTRA_VEZ = "Otra vez el bug de la pared en el nivel 3, ya van 3 veces que me pasa."
JEFE_FINAL = "El jefe final es demasiado dificil comparado con el resto del juego."
JEFE_ROTO = "El jefe final sigue completamente roto."
BASURA = "Este juego es una basura total, quien lo hizo no tiene idea de nada."
CITA_V05 = "Esto ya me pasaba en la v0.5 y todavia no lo arreglan."
INVENTARIO = "El menu de inventario mejoro bastante desde la ultima vez."

BUILD = "v0.8.2"


@pytest.fixture
def lote():
    """Construye un `PlaytestBatch`. Por defecto: 2 comentarios y build v0.8.2."""

    def _lote(
        textos: tuple[str, ...] = (BUG_PARED, JEFE_FINAL),
        build: str | None = BUILD,
        fuente: str = "discord",
    ) -> PlaytestBatch:
        return PlaytestBatch(
            build=build,
            comentarios=[PlaytestComment(fuente=fuente, texto=t) for t in textos],
        )

    return _lote


@pytest.fixture
def reporte():
    """Un `FeedbackReport` correcto para ese lote, con los cambios que se pidan."""

    def _reporte(batch: PlaytestBatch, **cambios) -> FeedbackReport:
        datos = {
            "resumen_general": "Reporte de prueba.",
            "sentimiento_general": "negativo",
            "version_juego": batch.build,
            "total_comentarios_analizados": batch.total,
            "requiere_revision_humana": False,
            "problemas_detectados": [],
            "comentarios_evidencia": [],
            "comentarios_descartados": [],
        }
        datos.update(cambios)
        return FeedbackReport.model_validate(datos)

    return _reporte


def problema(**cambios) -> dict:
    """Un `DetectedIssue` valido, con los cambios que se pidan."""
    base = {
        "categoria": "bugs",
        "descripcion": "El personaje se queda atascado en la pared del nivel 3.",
        "frecuencia": 1,
        "prioridad": "alta",
        "fuente_predominante": "discord",
    }
    base.update(cambios)
    return base

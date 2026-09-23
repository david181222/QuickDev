"""El resultado de analizar un lote.

Responsabilidad: ser el dato que la capa de aplicacion devuelve al mundo (CLI,
evals, notebook).
"""

from dataclasses import dataclass, field

from quickdev.domain.models import FeedbackReport
from quickdev.domain.rules.base import Finding
from quickdev.observability.trace import Trace


@dataclass
class AnalysisResult:
    """Lo que sale de analizar un lote.

    `report` y `raw_report` son distintos a proposito y ninguno sobra:

    - `raw_report` es el JSON que devolvio el modelo, sin tocar.
    - `report` es el reporte ya validado y reparado, que es el que se entrega.

    Los evals evaluan cada asercion contra los dos, y la diferencia entre las dos
    lecturas es lo que distingue "fallo el prompt" (fallo en crudo, lo salvo el
    codigo) de "falto validacion" (fallo en crudo y sigue fallando despues). Sin
    conservar el crudo, esa pregunta no se puede responder.
    """

    report: FeedbackReport
    raw_report: dict
    findings: list[Finding] = field(default_factory=list)
    trace: Trace | None = None

    @property
    def approved(self) -> bool:
        """True si ninguna regla encontro nada. Sin hallazgos, sin correcciones."""
        return not self.findings

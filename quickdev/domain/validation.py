"""Detectar y reparar, separados.

STUB DE CONTRATO. Las firmas son definitivas; los cuerpos los implementa
`core/edwin`.

Por que estan separados: `validate_output` (`evals/motor.py:91-203`) hacia las
dos cosas a la vez y devolvia `output_corregido`, sobrescribiendo el total,
poniendo `version_juego` en None y forzando `requiere_revision_humana`. Eso hace
imposible preguntar "que esta mal" sin que el sistema ya lo haya arreglado, y
mezcla dos politicas que cambian por razones distintas. Ver ADR-0004.
"""

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, RuleSet


class Validator:
    """Corre un conjunto de reglas sobre un reporte. Solo detecta.

    No modifica el reporte. No decide que hacer con lo que encuentra.
    """

    def __init__(self, rules: RuleSet) -> None:
        self.rules = rules

    def validate(self, report: FeedbackReport, batch: PlaytestBatch) -> list[Finding]:
        """Devuelve todos los hallazgos, en el orden de las reglas del conjunto."""
        raise NotImplementedError("Lo implementa core/edwin (domain/validation.py).")


class RepairPolicy:
    """Decide que se corrige, que se deja y que exige revision humana.

    La politica es explicita y consultable a proposito: "el codigo corrige en
    silencio" es exactamente la clase de comportamiento que un producto cuya
    promesa es la auditabilidad no puede permitirse sin dejar rastro.

    Regla de negocio que viene del validador original y se conserva: cualquier
    hallazgo fuerza `requiere_revision_humana = True`.
    """

    def repair(
        self,
        report: FeedbackReport,
        batch: PlaytestBatch,
        findings: list[Finding],
    ) -> FeedbackReport:
        """Devuelve un reporte nuevo con las correcciones aplicadas.

        No muta el reporte recibido: el crudo del modelo se conserva intacto para
        que los evals puedan evaluar las aserciones contra las dos versiones. Esa
        diferencia es lo que distingue "fallo el prompt" de "falto validacion".
        """
        raise NotImplementedError("Lo implementa core/edwin (domain/validation.py).")

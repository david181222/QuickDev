"""Detectar y reparar, separados.

Por que estan separados: `validate_output` (`evals/motor.py:91-203`) hacia las dos
cosas a la vez y devolvia `output_corregido`, sobrescribiendo el total, poniendo
`version_juego` en None y forzando `requiere_revision_humana`. Eso hace imposible
preguntar "que esta mal" sin que el sistema ya lo haya arreglado, y suelda dos
politicas que cambian por razones distintas. Ver ADR-0004.
"""

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, RuleSet


class Validator:
    """Corre un conjunto de reglas sobre un reporte. Solo detecta.

    No modifica el reporte y no decide que hacer con lo que encuentra.
    """

    def __init__(self, rules: RuleSet) -> None:
        self.rules = rules

    @property
    def version(self) -> str:
        """La version del conjunto de reglas. Se estampa en cada corrida."""
        return self.rules.version

    def validate(self, report: FeedbackReport, batch: PlaytestBatch) -> list[Finding]:
        """Todos los hallazgos, en el orden de las reglas del conjunto."""
        hallazgos: list[Finding] = []
        for regla in self.rules:
            hallazgos.extend(regla.check(report, batch))
        return hallazgos


class RepairPolicy:
    """Decide que se corrige, que se deja y que exige revision humana.

    La politica es una tabla explicita y no logica repartida entre las reglas,
    porque "el codigo corrige en silencio" es precisamente lo que un producto
    cuya promesa es la auditabilidad no puede permitirse sin dejar rastro. Esta
    clase es el unico sitio del sistema que modifica un reporte, y se puede leer
    de una sentada.

    Que se corrige, por `rule_id`:

    | rule_id                    | correccion                              |
    |----------------------------|-----------------------------------------|
    | total_matches_batch        | el total pasa a ser `batch.total`       |
    | version_appears_literally  | `version_juego` pasa a null             |
    | version_is_analyzed_build  | `version_juego` pasa a ser `batch.build`|
    | frequency_within_total     | NADA: se reporta, no se inventa un dato |
    | quotes_are_literal         | NADA: no se puede adivinar la cita real |
    | *_requires_review          | revision humana a true                  |

    Y una regla global: CUALQUIER hallazgo fuerza `requiere_revision_humana` a
    true. Un reporte que afirma algo falso no sale sin pasar por una persona.
    """

    # Reglas que solo informan. Corregirlas seria fabricar el dato que falta, que
    # es justo lo que el producto promete no hacer.
    SOLO_INFORMAN = frozenset({"frequency_within_total", "quotes_are_literal"})

    def repair(
        self,
        report: FeedbackReport,
        batch: PlaytestBatch,
        findings: list[Finding],
    ) -> FeedbackReport:
        """Un reporte NUEVO con las correcciones aplicadas.

        No muta el que recibe: el crudo del modelo se conserva intacto para que
        los evals puedan evaluar sus aserciones contra las dos versiones. Esa
        diferencia es lo que distingue "fallo el prompt" de "falto validacion".
        """
        if not findings:
            return report

        datos = report.model_dump()
        ids = {f.rule_id for f in findings}

        if "total_matches_batch" in ids:
            datos["total_comentarios_analizados"] = batch.total

        if "version_appears_literally" in ids:
            datos["version_juego"] = None

        if "version_is_analyzed_build" in ids and datos["version_juego"] is not None:
            # Cuando el reporte trae una version equivocada, la correcta es la
            # build del lote. Si el reporte venia en null, no hay nada que
            # corregir: el dato falta, y forzar un valor seria inventarlo.
            datos["version_juego"] = batch.build

        # Cualquier hallazgo, del tipo que sea, exige confirmacion humana.
        datos["requiere_revision_humana"] = True

        return FeedbackReport.model_validate(datos)

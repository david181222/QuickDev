"""Reglas que exigen revision humana.

Estas reglas no comprueban si el reporte dice la verdad: comprueban si el sistema
esta tomando sola una decision que le corresponde a una persona. Son la
implementacion del `human_decision` del contrato.
"""

from collections.abc import Iterable

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, Severity
from quickdev.domain.rules.versioning import menciones_de_version

_MOTIVOS_QUE_EXIGEN_REVISION = {"sesgado", "extremista"}


class DiscardedBiasRequiresReview:
    """Descartar por sesgo o extremismo exige revision humana.

    Vale para las dos versiones del conjunto de reglas.

    Descartar es una decision de EXCLUSION: el sistema esta eligiendo que
    feedback no se lee. Cuando el motivo es un juicio sobre el tono de quien
    escribio -y no un hecho comprobable como "no habla del juego"- esa decision
    la confirma una persona.
    """

    id = "discarded_bias_requires_review"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        motivos = {d.motivo for d in report.comentarios_descartados}
        if motivos & _MOTIVOS_QUE_EXIGEN_REVISION and not report.requiere_revision_humana:
            yield Finding(
                rule_id=self.id,
                field="requiere_revision_humana",
                message="hay comentarios sesgados o extremistas y no se marco revision humana",
                severity=Severity.CRITICAL,
            )


class MultipleBuildsRequireReview:
    """Solo `after`. Si el lote menciona mas de una build, decide una persona.

    Salio del diagnostico del baseline: cuando hay dos versiones en juego, el
    reporte agregado puede estar mezclando feedback de builds distintas, y eso no
    lo resuelve una regla de texto.
    """

    id = "multiple_builds_require_review"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        if len(menciones_de_version(batch)) > 1 and not report.requiere_revision_humana:
            yield Finding(
                rule_id=self.id,
                field="requiere_revision_humana",
                message=(
                    "el lote menciona mas de una version de build y no se marco revision humana"
                ),
                severity=Severity.CRITICAL,
            )


class AnyDiscardRequiresReview:
    """Solo `after`. Cualquier descarte exige revision humana, no solo el sesgado.

    Generaliza `DiscardedBiasRequiresReview`: si el sistema decidio no leer algo,
    la confirmacion es humana sea cual sea el motivo. Se anadio en `after` porque
    el baseline dejaba pasar descartes por "ruido" o "sin_relacion" sin que nadie
    los mirara.
    """

    id = "any_discard_requires_review"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        if report.comentarios_descartados and not report.requiere_revision_humana:
            yield Finding(
                rule_id=self.id,
                field="requiere_revision_humana",
                message="se descartaron comentarios y no se marco revision humana",
                severity=Severity.CRITICAL,
            )

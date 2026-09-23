"""Reglas de conteo. Contar es trabajo del codigo, no del modelo.

El prompt le pide al modelo que cuente los comentarios uno por uno. Estas reglas
son la garantia: comparan lo que dijo contra `len()`.
"""

from collections.abc import Iterable

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, Severity


class TotalMatchesBatch:
    """`total_comentarios_analizados` debe ser el conteo real del lote.

    Es la regla que existe porque el input viejo decia "214 comentarios" y
    listaba 8, asi que el modelo no tenia mas remedio que fabricar la cifra.
    """

    id = "total_matches_batch"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        if report.total_comentarios_analizados != batch.total:
            yield Finding(
                rule_id=self.id,
                field="total_comentarios_analizados",
                message=(
                    f"total_comentarios_analizados={report.total_comentarios_analizados} "
                    f"pero el lote tiene {batch.total}"
                ),
                severity=Severity.CRITICAL,
            )


class FrequencyWithinTotal:
    """Ninguna frecuencia puede superar el total de comentarios del lote.

    El tipo ya garantiza `frecuencia >= 1` y que sea entero; la cota superior
    depende del lote, asi que no se puede expresar en el tipo y hace falta regla.

    Limite conocido: comprueba la cota, no el valor. Una frecuencia de 3 sobre un
    lote de 14 pasa aunque sea inventada. Cerrar ese hueco es lo que propone el
    ADR-0005 (evidencia por indice).
    """

    id = "frequency_within_total"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        for i, problema in enumerate(report.problemas_detectados):
            if problema.frecuencia > batch.total:
                yield Finding(
                    rule_id=self.id,
                    field=f"problemas_detectados[{i}].frecuencia",
                    message=(
                        f"problema {i}: frecuencia {problema.frecuencia} "
                        f"supera el total {batch.total}"
                    ),
                    severity=Severity.CRITICAL,
                )

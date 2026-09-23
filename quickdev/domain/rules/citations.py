"""Reglas de citas. Toda cita debe existir literalmente en el lote.

Es la regla que sostiene la auditabilidad del producto: si las citas no son
literales, el desarrollador no puede volver al comentario original y el reporte
deja de ser verificable. Un resumen bonito, pero no una evidencia.
"""

import re
from collections.abc import Iterable

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, Severity


def _normalizar(texto: str | None) -> str:
    """Quita comillas envolventes y colapsa espacios.

    El modelo a veces devuelve la cita con comillas o con el espaciado alterado.
    Eso no es una cita distinta, asi que normalizar evita falsos positivos sin
    aflojar la regla.
    """
    limpio = (texto or "").strip().strip('"').strip()
    return re.sub(r"\s+", " ", limpio)


class QuotesAreLiteral:
    """El texto de cada cita debe aparecer en algun comentario del lote.

    La comprobacion es en UNA SOLA DIRECCION: la cita tiene que estar contenida
    en un comentario real.

    La implementacion original (`evals/motor.py:164`) aceptaba tambien la
    direccion inversa:

        any(t in real or real in t for real in textos_reales)

    Ese `real in t` deja pasar una cita que ENVUELVE un comentario real con texto
    inventado alrededor, que es exactamente lo que la regla promete impedir.
    Medido antes de cambiarlo: en las 132 citas de los 37 casos disponibles
    -las 7 regresiones y las 30 corridas guardadas en `crudo.json`- las dos
    versiones dan el mismo resultado, asi que el arreglo cierra el hueco sin
    alterar ninguna medicion. Ver ADR-0003.
    """

    id = "quotes_are_literal"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        reales = [_normalizar(c.texto) for c in batch.comentarios]

        def existe(texto: str | None) -> bool:
            cita = _normalizar(texto)
            return bool(cita) and any(cita in real for real in reales)

        for i, cita in enumerate(report.comentarios_evidencia):
            if not existe(cita.texto):
                yield Finding(
                    rule_id=self.id,
                    field=f"comentarios_evidencia[{i}].texto",
                    message=f"evidencia {i}: el texto citado no existe en el lote",
                    severity=Severity.CRITICAL,
                )

        for i, descartado in enumerate(report.comentarios_descartados):
            if not existe(descartado.texto):
                yield Finding(
                    rule_id=self.id,
                    field=f"comentarios_descartados[{i}].texto",
                    message=f"descartado {i}: el texto citado no existe en el lote",
                    severity=Severity.CRITICAL,
                )

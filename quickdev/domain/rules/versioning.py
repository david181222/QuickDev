"""Reglas de version de build. El edge case del producto vive aqui.

El caso: la build analizada es `v0.8.2`, pero un jugador cita la `v0.5` dentro de
su comentario. Las dos aparecen literalmente en el input, asi que la regla del
prompt -"la version debe aparecer literalmente"- no desempata. El baseline midio
0/3 en ese eval; el conjunto `after` lo lleva a 3/3.

Las dos versiones del conjunto de reglas se conservan a proposito: `baseline` es
el registro de lo que se midio, con su falso positivo incluido. No se arregla,
porque es la referencia contra la que se demuestra la mejora.
"""

import re
from collections.abc import Iterable

from quickdev.domain.models import FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding, Severity

# Detecta menciones de version tipo v0.8.2 o v1.0 en texto libre.
_VERSION = re.compile(r"\bv\d+(?:\.\d+)+\b", flags=re.IGNORECASE)


def _aparece_en_el_lote(texto: str | None, batch: PlaytestBatch) -> bool:
    """Si esa cadena esta literalmente en la build declarada o en algun comentario."""
    if texto is None:
        return False
    aguja = str(texto)
    if batch.build and aguja in batch.build:
        return True
    return any(aguja in c.texto for c in batch.comentarios)


def _version_efectiva(report: FeedbackReport, batch: PlaytestBatch) -> str | None:
    """El valor de `version_juego` una vez descartado lo no literal.

    Las reglas que siguen dependen de este valor, no del crudo. Es una
    transcripcion fiel del validador original, donde la comprobacion de nulidad
    se hacia DESPUES de que la comprobacion de literalidad hubiera puesto el
    campo en None. Sin esta funcion, un `version_juego` inventado produciria un
    hallazgo en vez de dos, y el conjunto `baseline` dejaria de reproducir lo
    medido.
    """
    version = report.version_juego
    if version is not None and not _aparece_en_el_lote(version, batch):
        return None
    return version


class VersionAppearsLiterally:
    """`version_juego`, si no es null, debe aparecer literalmente en el lote.

    Vale para las dos versiones del conjunto de reglas. Es la alucinacion mas
    cara que puede cometer el producto: una version inventada manda al equipo a
    revisar la build equivocada, y el reporte se ve igual de convincente.
    """

    id = "version_appears_literally"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        version = report.version_juego
        if version is not None and not _aparece_en_el_lote(version, batch):
            yield Finding(
                rule_id=self.id,
                field="version_juego",
                message=f"version_juego='{version}' no aparece literalmente en el input",
                severity=Severity.CRITICAL,
            )


class VersionIsNotNull:
    """Solo `baseline`. FALSO POSITIVO CONSERVADO A PROPOSITO.

    Marca fallo siempre que `version_juego` quede en null, incluso cuando el lote
    legitimamente no trae version. En el diagnostico del baseline este hallazgo
    aparece en 4 de los 5 evals y tapa los fallos reales, que era justo el
    problema que el diagnostico revelo.

    No se corrige aqui: se corrige en el conjunto `after`, con
    `VersionIsAnalyzedBuild`. Esta clase existe para que la medicion guardada
    siga siendo reproducible.
    """

    id = "version_is_not_null"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        if _version_efectiva(report, batch) is None:
            yield Finding(
                rule_id=self.id,
                field="version_juego",
                message="version_juego es null",
                severity=Severity.WARNING,
            )


class VersionIsAnalyzedBuild:
    """Solo `after`. `version_juego` es la build analizada y ninguna otra.

    Tres formas de incumplirla, con mensajes distintos porque son problemas
    distintos:

    1. el lote no declara build y el reporte trae una;
    2. el lote declara build y el reporte trae null;
    3. el reporte trae una version que no es la build analizada -normalmente
       una que un jugador menciono dentro de su comentario.

    La 3 es el edge case del producto. Es la unica de las tres que el validador
    baseline no podia atrapar, porque la version citada SI aparece literalmente
    en el input.
    """

    id = "version_is_analyzed_build"

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        efectiva = _version_efectiva(report, batch)

        if batch.build is None:
            if efectiva is not None:
                yield Finding(
                    rule_id=self.id,
                    field="version_juego",
                    message=f"version_juego='{efectiva}' pero la build no fue especificada",
                    severity=Severity.CRITICAL,
                )
        elif efectiva is None:
            yield Finding(
                rule_id=self.id,
                field="version_juego",
                message=f"version_juego es null pero la build analizada es '{batch.build}'",
                severity=Severity.CRITICAL,
            )
        elif str(efectiva) != str(batch.build):
            yield Finding(
                rule_id=self.id,
                field="version_juego",
                message=(
                    f"version_juego='{efectiva}' no es la build analizada "
                    f"'{batch.build}' (probablemente una version citada dentro "
                    f"de un comentario)"
                ),
                severity=Severity.CRITICAL,
            )


def menciones_de_version(batch: PlaytestBatch) -> set[str]:
    """Las versiones distintas mencionadas en el lote, build declarada incluida.

    La usa `MultipleBuildsRequireReview`. Vive aqui porque el patron de version
    es de este modulo.
    """
    texto = (batch.build or "") + "\n" + "\n".join(c.texto for c in batch.comentarios)
    return set(_VERSION.findall(texto))

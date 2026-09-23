"""Que reglas componen cada version del validador.

Aqui esta la respuesta al `if modo == "baseline"` / `if modo == "after"` que
ramificaba por dentro de `validate_output` (`evals/motor.py:118` y `:183`). Una
version del validador deja de ser una rama dentro de una funcion y pasa a ser una
composicion distinta de las mismas piezas. Ver ADR-0003.

El ORDEN de las reglas importa: reproduce el orden en que el validador original
acumulaba sus fallos, y eso es lo que permite comparar los dos implementaciones
hallazgo por hallazgo (`tests/domain/test_equivalencia_baseline.py`).
"""

from quickdev.domain.rules.base import RuleSet
from quickdev.domain.rules.citations import QuotesAreLiteral
from quickdev.domain.rules.counts import FrequencyWithinTotal, TotalMatchesBatch
from quickdev.domain.rules.review import (
    AnyDiscardRequiresReview,
    DiscardedBiasRequiresReview,
    MultipleBuildsRequireReview,
)
from quickdev.domain.rules.versioning import (
    VersionAppearsLiterally,
    VersionIsAnalyzedBuild,
    VersionIsNotNull,
)

# Las dos versiones que estan MEDIDAS y commiteadas en evals/resultados/.
#
# "baseline": el validador original del notebook, falso positivo incluido
#             (VersionIsNotNull marca fallo aunque el lote legitimamente no
#             traiga version). Se conserva como registro historico: es la
#             referencia contra la que se demuestra la mejora. NO se arregla.
# "after":    el corregido tras el diagnostico. Cambia VersionIsNotNull por
#             VersionIsAnalyzedBuild y anade dos reglas de revision humana.
_VERSIONES: dict[str, tuple] = {
    "baseline": (
        TotalMatchesBatch(),
        VersionAppearsLiterally(),
        VersionIsNotNull(),
        FrequencyWithinTotal(),
        QuotesAreLiteral(),
        DiscardedBiasRequiresReview(),
    ),
    "after": (
        TotalMatchesBatch(),
        VersionAppearsLiterally(),
        VersionIsAnalyzedBuild(),
        FrequencyWithinTotal(),
        QuotesAreLiteral(),
        DiscardedBiasRequiresReview(),
        MultipleBuildsRequireReview(),
        AnyDiscardRequiresReview(),
    ),
}

RULE_SET_VERSIONS: tuple[str, ...] = tuple(_VERSIONES)


def rule_set(version: str) -> RuleSet:
    """Devuelve el conjunto de reglas de esa version.

    Args:
        version: uno de `RULE_SET_VERSIONS`.

    Raises:
        KeyError: si la version no existe.
    """
    if version not in _VERSIONES:
        raise KeyError(
            f"No existe el conjunto de reglas '{version}'. Un conjunto nuevo se "
            f"escribe DESPUES de leer el diagnostico de la corrida anterior, no "
            f"antes. Disponibles: {sorted(_VERSIONES)}"
        )
    return RuleSet(version=version, rules=_VERSIONES[version])

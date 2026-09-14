"""Que reglas componen cada version del validador.

STUB DE CONTRATO. La firma es definitiva; el cuerpo lo implementa `core/edwin`.

Existe ya en `main` para que las otras dos ramas puedan importar y tipar contra
`rule_set(...)` sin esperar a que el dominio este implementado.
"""

from quickdev.domain.rules.base import RuleSet

# Las dos versiones que ya estan MEDIDAS y commiteadas en evals/resultados/.
# Reproducirlas exactamente es la puerta de aceptacion del refactor.
#
# "baseline": el validador original del notebook, falso positivo incluido (marca
#             fallo cuando version_juego es null aunque el lote legitimamente no
#             traiga version). Se conserva a proposito como registro historico:
#             es la version contra la que se mide la mejora.
# "after":    el corregido tras el diagnostico, que compara version_juego contra
#             la build analizada del lote.
RULE_SET_VERSIONS: tuple[str, ...] = ("baseline", "after")


def rule_set(version: str) -> RuleSet:
    """Devuelve el conjunto de reglas de esa version.

    Args:
        version: uno de `RULE_SET_VERSIONS`.

    Raises:
        KeyError: si la version no existe. El mensaje debe listar las
            disponibles: un conjunto de reglas nuevo se escribe DESPUES de leer
            el diagnostico de la corrida anterior, no antes.
    """
    raise NotImplementedError("Lo implementa core/edwin (domain/rules/registry.py).")

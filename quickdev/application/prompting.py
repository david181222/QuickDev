"""De donde salen los prompts.

STUB DE CONTRATO. El Protocol es definitivo; `PromptRegistry` lo implementa
`core/jose`.

Los prompts estan hoy hardcodeados como strings dentro de `evals/motor.py`
(`_REGLAS_BASELINE` en :227 y `_REGLAS_AFTER` en :275). Salen a `prompts/*.md`
para que sean versionables y diffeables: un cambio de prompt es un cambio de
comportamiento, y tiene que poder revisarse como tal.
"""

from typing import Protocol

from quickdev.domain.models import PlaytestBatch


class PromptProvider(Protocol):
    """Provee el prompt de sistema y el payload de una version dada."""

    def system_prompt(self, version: str) -> str:
        """El texto del prompt de sistema de esa version.

        Raises:
            KeyError: si la version no existe, listando las disponibles.
        """
        ...

    def build_payload(self, batch: PlaytestBatch) -> dict:
        """Arma el payload de datos que acompana al prompt.

        Los comentarios viajan como array JSON, no como un string renderizado.
        La implementacion vieja (`evals/motor.py:312`) los concatenaba con
        comillas y saltos de linea, asi que un comentario de jugador que
        contuviera una comilla rompia el formato numerado del que dependia el
        conteo.
        """
        ...

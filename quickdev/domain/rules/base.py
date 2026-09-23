"""El contrato de una regla de validacion.

Responsabilidad: definir que es una regla, que devuelve y como se agrupan.

Lo que NO le corresponde: implementar reglas concretas (van en los modulos
hermanos: `counts.py`, `citations.py`, `versioning.py`, `enums.py`, `review.py`)
ni decidir que se corrige cuando una falla (eso es `domain/validation.py`).

Decision de diseno que conviene poder defender: una regla recibe el
`PlaytestBatch`, NO el texto renderizado del prompt. La implementacion vieja
(`evals/motor.py:91`) recibia `input_text: str` y comprobaba las citas por
substring contra ese string, lo que ataba el validador al formato del prompt: si
alguien cambiaba como se numeran los comentarios, la validacion cambiaba de
significado sin que nadie lo notara. Con el lote tipado, una cita se resuelve
contra `batch.comentarios[i].texto`. Ver ADR-0003.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from quickdev.domain.models import FeedbackReport, PlaytestBatch


class Severity(StrEnum):
    """Que tan grave es un hallazgo.

    CRITICAL: el reporte afirma algo falso (un conteo que no cuadra, una cita
    que nadie escribio, una version inventada). No puede entregarse asi.
    WARNING: el reporte es defendible pero incompleto o sospechoso.
    """

    CRITICAL = "critical"
    WARNING = "warning"


@dataclass(frozen=True)
class Finding:
    """Un hallazgo: una regla que no se cumplio.

    Es un dato, no un string formateado. La implementacion vieja acumulaba
    mensajes en una `list[str]`, asi que los evals tenian que buscar fragmentos
    de texto (`any("supera el total" in f for f in fallos)`) para saber que habia
    fallado. Con `rule_id` y `field` eso pasa a ser una consulta.
    """

    rule_id: str
    field: str
    message: str
    severity: Severity = Severity.CRITICAL


class Rule(Protocol):
    """Una comprobacion determinista sobre un reporte.

    Sin modelo, sin red, sin I/O: dado un reporte y el lote del que salio,
    devuelve los hallazgos que encuentre. Una regla que no encuentra nada
    devuelve una secuencia vacia.

    `id` identifica la regla en los hallazgos y en los reportes de evals, asi que
    es estable: cambiarlo rompe la comparabilidad con las mediciones guardadas.
    """

    id: str

    def check(self, report: FeedbackReport, batch: PlaytestBatch) -> Iterable[Finding]:
        """Devuelve los hallazgos de esta regla sobre este reporte."""
        ...


@dataclass(frozen=True)
class RuleSet:
    """Un conjunto de reglas con nombre de version.

    Esto es lo que reemplaza al parametro `modo="baseline"|"after"` que ramificaba
    por dentro de `validate_output` (`evals/motor.py:118` y `:183`). Una version
    del validador deja de ser una rama dentro de una funcion y pasa a ser una
    composicion distinta de las mismas piezas. Agregar una regla es agregar un
    archivo; agregar una version es componer una tupla. Ver ADR-0003.

    `version` se estampa en cada corrida de evals, asi que es parte del registro
    de trazabilidad: un resultado sin su `rules_version` no es comparable.
    """

    version: str
    rules: tuple[Rule, ...]

    def __iter__(self) -> Iterator[Rule]:
        return iter(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

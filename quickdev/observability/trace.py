"""La traza de una ejecucion del pipeline.

Responsabilidad: registrar que paso, en que orden, con que decision.

Lo que NO le corresponde: escribir archivos ni averiguar el `git_sha` (eso es
`RunManifest`, en `core/miguel`).

Este objeto hace dos trabajos a la vez, y por eso vale la pena:

1. Trazabilidad. Cada ejecucion queda con su registro paso a paso: que prompt,
   que reglas, que modelo, que decidio cada paso. Sin esto, comparar dos
   corridas es un acto de fe.
2. Preparacion para agente. Hoy los pasos son una secuencia fija
   (render -> call -> parse -> validate -> repair). El dia que los decida un
   bucle en vez de una lista, el registro es exactamente el mismo y el dominio
   no cambia. Esa es la costura.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class TraceStep:
    """Un paso ejecutado.

    `decision` es texto legible por una persona: que se decidio y por que, no un
    volcado del estado. Es lo que alguien lee cuando pregunta "por que este
    reporte salio con revision humana en true".
    """

    name: str
    decision: str
    started_at: str = field(default_factory=_now_iso)
    duration_s: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "decision": self.decision,
            "started_at": self.started_at,
            "duration_s": round(self.duration_s, 3),
            "metadata": self.metadata,
        }


@dataclass
class Trace:
    """El registro completo de una ejecucion.

    Las cuatro versiones (`prompt_version`, `rules_version`, `schema_version`,
    `model`) mas el `git_sha` son lo que hace comparable una medicion. Una fila
    de resultados sin ese estampado no se puede contrastar contra otra: no hay
    nada en el archivo que diga que la produjo.
    """

    prompt_version: str
    rules_version: str
    schema_version: str
    model: str
    git_sha: str = ""
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    started_at: str = field(default_factory=_now_iso)
    steps: list[TraceStep] = field(default_factory=list)

    def add_step(
        self,
        name: str,
        decision: str,
        duration_s: float = 0.0,
        **metadata: object,
    ) -> TraceStep:
        """Registra un paso y lo devuelve."""
        step = TraceStep(
            name=name,
            decision=decision,
            duration_s=duration_s,
            metadata=dict(metadata),
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> dict:
        """Forma serializable, para el manifiesto de corrida y los reportes."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "prompt_version": self.prompt_version,
            "rules_version": self.rules_version,
            "schema_version": self.schema_version,
            "model": self.model,
            "git_sha": self.git_sha,
            "steps": [s.to_dict() for s in self.steps],
        }

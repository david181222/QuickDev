"""El caso de uso: analizar un lote de feedback de playtest.

STUB DE CONTRATO. La firma es definitiva; el cuerpo lo implementa `core/edwin`.

Esta es la unica clase que conoce el orden completo del flujo. Nada por debajo
de ella sabe que existe un modelo, y nada por encima sabe como se valida.

Se estructura como una SECUENCIA EXPLICITA DE PASOS, cada uno registrando su
decision en el `Trace`:

    render_prompt -> call_model -> parse_report -> validate -> repair_or_retry

No como una funcion que hace cinco cosas. La diferencia importa porque este es un
MVP de algo que va a ser un agente: el dia que los pasos los decida un bucle en
vez de una lista, la interfaz y el registro son los mismos.
"""

from quickdev.application.prompting import PromptProvider
from quickdev.application.types import AnalysisResult
from quickdev.config import Settings
from quickdev.domain.models import PlaytestBatch
from quickdev.domain.validation import RepairPolicy, Validator
from quickdev.ports.llm import LlmPort


class AnalyzeBatch:
    """Convierte un lote de comentarios en un reporte validado."""

    def __init__(
        self,
        llm: LlmPort,
        validator: Validator,
        repair: RepairPolicy,
        prompts: PromptProvider,
        settings: Settings,
    ) -> None:
        self.llm = llm
        self.validator = validator
        self.repair = repair
        self.prompts = prompts
        self.settings = settings

    def execute(self, batch: PlaytestBatch) -> AnalysisResult:
        """Corre el pipeline completo sobre un lote.

        La ronda de reparacion con retroalimentacion al modelo (devolverle los
        hallazgos y pedirle que corrija solo esos campos) queda implementada pero
        APAGADA por defecto, detras de `settings.repair_round_enabled`. Se
        enciende cuando haya una medicion de pass@1 contra pass@2 que lo
        justifique, no antes.
        """
        raise NotImplementedError("Lo implementa core/edwin (application/analyze_batch.py).")

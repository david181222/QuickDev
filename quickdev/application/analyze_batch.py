"""El caso de uso: analizar un lote de feedback de playtest.

Esta es la unica clase que conoce el orden completo del flujo. Nada por debajo de
ella sabe que existe un modelo, y nada por encima sabe como se valida.

Se estructura como una SECUENCIA EXPLICITA DE PASOS, cada uno registrando su
decision en el `Trace`, y no como una funcion que hace cinco cosas:

    1. render_prompt   arma el prompt y el payload
    2. call_model      cruza el puerto LlmPort
    3. parse_report    dict -> FeedbackReport (la forma se valida aqui)
    4. validate        las reglas deterministas, sin modelo
    5. repair_or_retry corrige, o pide al modelo que corrija

La diferencia importa porque esto es un MVP de algo que va a ser un agente: el
dia que los pasos los decida un bucle en vez de una lista, la interfaz de
`execute` y el registro del `Trace` son los mismos, y el dominio no cambia.
"""

import time

from quickdev.application.prompting import PromptProvider
from quickdev.application.types import AnalysisResult
from quickdev.config import Settings
from quickdev.domain.models import SCHEMA_VERSION, FeedbackReport, PlaytestBatch
from quickdev.domain.rules.base import Finding
from quickdev.domain.validation import RepairPolicy, Validator
from quickdev.observability.trace import Trace
from quickdev.ports.llm import LlmPort, LlmRequest, LlmResponse

# Los pasos, en orden. Es la costura para el bucle de agente: hoy esta lista es
# fija, manana la decide algo mas, y el registro no cambia.
PASOS = ("render_prompt", "call_model", "parse_report", "validate", "repair_or_retry")


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

    # -- el flujo -----------------------------------------------------------

    def execute(self, batch: PlaytestBatch) -> AnalysisResult:
        """Corre el pipeline completo sobre un lote."""
        trace = Trace(
            prompt_version=self.settings.prompt_version,
            rules_version=self.validator.version,
            schema_version=SCHEMA_VERSION,
            model=self.settings.model,
        )

        system_prompt, payload = self._render_prompt(batch, trace)
        respuesta = self._call_model(system_prompt, payload, trace)
        report = self._parse_report(respuesta, trace)
        hallazgos = self._validate(report, batch, trace)
        final, hallazgos = self._repair_or_retry(
            report, batch, hallazgos, system_prompt, payload, trace
        )

        return AnalysisResult(
            report=final,
            raw_report=respuesta.data,
            findings=hallazgos,
            trace=trace,
        )

    # -- los pasos ----------------------------------------------------------

    def _render_prompt(self, batch: PlaytestBatch, trace: Trace) -> tuple[str, dict]:
        inicio = time.perf_counter()
        version = self.settings.prompt_version
        system_prompt = self.prompts.system_prompt(version)
        payload = self.prompts.build_payload(batch)
        trace.add_step(
            "render_prompt",
            f"prompt '{version}' con {batch.total} comentarios",
            duration_s=time.perf_counter() - inicio,
            prompt_version=version,
            comentarios=batch.total,
            build=batch.build,
        )
        return system_prompt, payload

    def _call_model(self, system_prompt: str, payload: dict, trace: Trace) -> LlmResponse:
        inicio = time.perf_counter()
        respuesta = self.llm.complete_json(
            LlmRequest(
                system_prompt=system_prompt,
                payload=payload,
                # La forma la garantiza el proveedor, no una instruccion del
                # prompt. Ver ADR-0009.
                response_schema=FeedbackReport,
                max_output_tokens=self.settings.max_output_tokens,
                temperature=self.settings.temperature,
            )
        )
        cache = " (cache)" if respuesta.from_cache else ""
        trace.add_step(
            "call_model",
            f"{respuesta.attempts} intento(s){cache}",
            duration_s=time.perf_counter() - inicio,
            attempts=respuesta.attempts,
            truncated=respuesta.truncated,
            from_cache=respuesta.from_cache,
            latency_s=respuesta.latency_s,
        )
        return respuesta

    def _parse_report(self, respuesta: LlmResponse, trace: Trace) -> FeedbackReport:
        inicio = time.perf_counter()
        report = FeedbackReport.model_validate(respuesta.data)
        trace.add_step(
            "parse_report",
            f"forma valida contra el esquema {SCHEMA_VERSION}",
            duration_s=time.perf_counter() - inicio,
            schema_version=SCHEMA_VERSION,
        )
        return report

    def _validate(
        self, report: FeedbackReport, batch: PlaytestBatch, trace: Trace
    ) -> list[Finding]:
        inicio = time.perf_counter()
        hallazgos = self.validator.validate(report, batch)
        trace.add_step(
            "validate",
            f"{len(hallazgos)} hallazgo(s) con las reglas '{self.validator.version}'",
            duration_s=time.perf_counter() - inicio,
            rules_version=self.validator.version,
            findings=[h.rule_id for h in hallazgos],
        )
        return hallazgos

    def _repair_or_retry(
        self,
        report: FeedbackReport,
        batch: PlaytestBatch,
        hallazgos: list[Finding],
        system_prompt: str,
        payload: dict,
        trace: Trace,
    ) -> tuple[FeedbackReport, list[Finding]]:
        """Corrige con codigo o, si esta habilitado, pide al modelo que corrija.

        La ronda de reparacion esta APAGADA por defecto
        (`Settings.repair_round_enabled`). Se enciende cuando haya una medicion de
        pass@1 contra pass@2 que la justifique, no antes: encenderla sin medirla
        seria exactamente lo que este proyecto dice no hacer.
        """
        inicio = time.perf_counter()

        if not hallazgos:
            trace.add_step(
                "repair_or_retry",
                "sin hallazgos: nada que corregir",
                duration_s=time.perf_counter() - inicio,
            )
            return report, hallazgos

        if self.settings.repair_round_enabled:
            reintentado, nuevos = self._una_ronda_con_el_modelo(
                report, batch, hallazgos, system_prompt, payload, trace
            )
            if reintentado is not None and len(nuevos) < len(hallazgos):
                report, hallazgos = reintentado, nuevos

        corregido = self.repair.repair(report, batch, hallazgos)
        trace.add_step(
            "repair_or_retry",
            (
                f"{len(hallazgos)} hallazgo(s) corregidos por codigo; "
                f"revision humana = {corregido.requiere_revision_humana}"
            ),
            duration_s=time.perf_counter() - inicio,
            findings=[h.rule_id for h in hallazgos],
            requiere_revision_humana=corregido.requiere_revision_humana,
        )
        return corregido, hallazgos

    def _una_ronda_con_el_modelo(
        self,
        report: FeedbackReport,
        batch: PlaytestBatch,
        hallazgos: list[Finding],
        system_prompt: str,
        payload: dict,
        trace: Trace,
    ) -> tuple[FeedbackReport | None, list[Finding]]:
        """Le devuelve los hallazgos al modelo y le pide corregir solo esos campos.

        Devuelve `(None, [])` si el reintento no sirve, para que el llamador se
        quede con el primer reporte. Un fallo de esta ronda no debe tumbar el
        analisis: el camino de correccion por codigo sigue disponible.
        """
        inicio = time.perf_counter()
        reintento = dict(payload)
        reintento["reporte_anterior"] = report.model_dump()
        reintento["corregir_solo_estos_campos"] = [
            {"campo": h.field, "problema": h.message} for h in hallazgos
        ]

        try:
            respuesta = self.llm.complete_json(
                LlmRequest(
                    system_prompt=system_prompt,
                    payload=reintento,
                    response_schema=FeedbackReport,
                    max_output_tokens=self.settings.max_output_tokens,
                    temperature=self.settings.temperature,
                )
            )
            candidato = FeedbackReport.model_validate(respuesta.data)
            nuevos = self.validator.validate(candidato, batch)
        except Exception as exc:
            trace.add_step(
                "repair_round",
                f"descartada: {type(exc).__name__}",
                duration_s=time.perf_counter() - inicio,
                error=str(exc)[:200],
            )
            return None, []

        trace.add_step(
            "repair_round",
            f"{len(hallazgos)} hallazgo(s) -> {len(nuevos)}",
            duration_s=time.perf_counter() - inicio,
            antes=len(hallazgos),
            despues=len(nuevos),
            aceptada=len(nuevos) < len(hallazgos),
        )
        return candidato, nuevos

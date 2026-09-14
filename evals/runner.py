"""Orquestacion de una corrida de evals. Solo eso.

Responsabilidad: para cada caso, correr el pipeline n veces y recoger lo que
paso.

Lo que NO le corresponde: definir casos (`cases.py`), derivar el diagnostico
(`diagnosis.py`), escribir archivos (`reporting.py`) ni saber que proveedor hay
detras del puerto.

## Corre el pipeline de verdad

Este runner no reimplementa el flujo: construye `AnalyzeBatch` y lo ejecuta. Es
lo que hace que el eval mida el producto y no una copia del producto que puede
divergir. El harness viejo tenia su propia `validate_output` y su propio cliente,
y precisamente por eso el validador del notebook y el de `evals/motor.py` ya
habian divergido cuando empezo esta migracion.

## Que se mide dos veces

Cada asercion se evalua contra el output CRUDO del modelo y contra el REPARADO
por el validador. La diferencia es lo que separa "fallo el prompt" de "falto
validacion", y es lo mejor que tiene este harness.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

from evals.cases import EVALS, EvalCase, Resultado
from evals.diagnosis import UMBRALES_POR_DEFECTO, Umbrales, diagnosticar
from evals.prompts_legacy import LegacyPromptProvider
from evals.regressions import run_regresiones
from quickdev.adapters import build_llm
from quickdev.adapters.fake import FakeLlm
from quickdev.application.analyze_batch import AnalyzeBatch
from quickdev.application.prompting import PromptProvider
from quickdev.config import Settings
from quickdev.domain.models import SCHEMA_VERSION
from quickdev.domain.rules.registry import rule_set
from quickdev.domain.validation import RepairPolicy, Validator
from quickdev.observability.manifest import RunManifest
from quickdev.ports.llm import LlmPort, LlmRequest, LlmResponse

DIR = Path(__file__).resolve().parent


class _MedidorLlm:
    """Envuelve el puerto para alimentar el manifiesto. No altera la respuesta.

    Existe para que el manifiesto se entere de cada llamada sin que el runner
    tenga que rebuscar los datos en la traza. Es un decorador mas del mismo
    puerto: la composicion sigue siendo la del ADR-0006.
    """

    def __init__(self, inner: LlmPort, manifest: RunManifest) -> None:
        self.inner = inner
        self.manifest = manifest
        self.ultima: LlmResponse | None = None

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        try:
            respuesta = self.inner.complete_json(request)
        except Exception as exc:
            self.manifest.record_error(exc)
            raise
        self.manifest.record_call(respuesta)
        self.ultima = respuesta
        return respuesta


@dataclass
class Corrida:
    """Todo lo que define una corrida de evals, junto y estampado."""

    prompt_version: str
    rules_version: str
    n: int
    settings: Settings
    llm: LlmPort
    prompts: PromptProvider
    umbrales: Umbrales = UMBRALES_POR_DEFECTO
    es_replay: bool = False
    manifest: RunManifest = field(init=False)

    def __post_init__(self) -> None:
        self.manifest = RunManifest(
            prompt_version=self.prompt_version,
            rules_version=self.rules_version,
            schema_version=SCHEMA_VERSION,
            model="replay" if self.es_replay else self.settings.model,
            n_corridas=self.n,
        )
        if self.es_replay:
            self.manifest.notas["replay"] = (
                "Reproduccion de outputs ya medidos. No se llamo a la API."
            )


def construir_corrida(
    prompt_version: str = "baseline",
    rules_version: str | None = None,
    n: int | None = None,
    replay: Path | None = None,
    settings: Settings | None = None,
    umbrales: Umbrales = UMBRALES_POR_DEFECTO,
) -> Corrida:
    """Arma la corrida: que prompt, que reglas, cuantas veces y contra que modelo.

    En modo replay, si no se pide un `n` explicito se usa el numero de corridas
    que hay grabadas, y se dice. Si se pide un `n` mayor del que hay, falla:
    encogerlo en silencio es el bug de `motor.py:429-431`.
    """
    rules_version = rules_version or prompt_version
    settings = settings or Settings(prompt_version=prompt_version, rules_version=rules_version)

    if replay is not None:
        fake = FakeLlm.from_crudo(replay)
        disponibles = fake.max_corridas
        if n is None:
            n = disponibles
        elif n > disponibles:
            raise ValueError(
                f"Se pidieron n={n} corridas pero {replay} solo tiene {disponibles} "
                f"grabadas por caso. En replay, n no se encoge en silencio: baja n "
                f"o vuelve a medir contra la API."
            )
        return Corrida(
            prompt_version=prompt_version,
            rules_version=rules_version,
            n=n,
            settings=settings,
            llm=fake,
            prompts=LegacyPromptProvider(),
            umbrales=umbrales,
            es_replay=True,
        )

    return Corrida(
        prompt_version=prompt_version,
        rules_version=rules_version,
        n=n or settings.eval_runs,
        settings=settings,
        llm=build_llm(settings),
        prompts=LegacyPromptProvider(),
        umbrales=umbrales,
    )


# ---------------------------------------------------------------------------


def correr_eval(case: EvalCase, corrida: Corrida) -> list[dict]:
    """Corre un caso n veces y devuelve una fila por corrida."""
    medidor = _MedidorLlm(corrida.llm, corrida.manifest)
    caso_de_uso = AnalyzeBatch(
        llm=medidor,
        validator=Validator(rule_set(corrida.rules_version)),
        repair=RepairPolicy(),
        prompts=corrida.prompts,
        settings=corrida.settings,
    )

    filas = []
    for i in range(1, corrida.n + 1):
        filas.append(_una_corrida(case, corrida, caso_de_uso, medidor, i))
    return filas


def _una_corrida(
    case: EvalCase,
    corrida: Corrida,
    caso_de_uso: AnalyzeBatch,
    medidor: _MedidorLlm,
    i: int,
) -> dict:
    """Una ejecucion del pipeline sobre un caso, con sus aserciones evaluadas."""
    fila = {
        "eval_id": case.id,
        "categoria": case.categoria,
        "corrida": i,
        "prompt_version": corrida.prompt_version,
        "rules_version": corrida.rules_version,
    }
    inicio = time.perf_counter()

    try:
        resultado = caso_de_uso.execute(case.batch)
    except Exception as exc:
        # Una corrida que murio se registra como corrida muerta, con su motivo.
        # Lo que NO se hace es saltarla: n tiene que seguir siendo n.
        fila.update(
            {
                "tool_ok": False,
                "intentos": medidor.ultima.attempts if medidor.ultima else 1,
                "truncado": False,
                "from_cache": False,
                "latencia_s": round(time.perf_counter() - inicio, 2),
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "asserts_crudo": {},
                "asserts_corregido": {},
                "errores_assert": {},
                "hallazgos": [],
                "fallos_validacion": None,
                "paso": False,
            }
        )
        return fila

    crudo = resultado.raw_report
    reparado = resultado.report.model_dump()
    a_crudo, errores = _evaluar(case, crudo)
    a_reparado, errores_reparado = _evaluar(case, reparado)
    errores.update(errores_reparado)

    respuesta = medidor.ultima
    fila.update(
        {
            "tool_ok": True,
            "intentos": respuesta.attempts if respuesta else 1,
            "truncado": bool(respuesta.truncated) if respuesta else False,
            "from_cache": bool(respuesta.from_cache) if respuesta else False,
            "latencia_s": round(respuesta.latency_s, 2) if respuesta else 0.0,
            "error": None,
            "input": corrida.prompts.build_payload(case.batch).get("input"),
            "output_crudo": crudo,
            "output_corregido": reparado,
            "hallazgos": [h.rule_id for h in resultado.findings],
            "detalle_hallazgos": [h.message for h in resultado.findings],
            "fallos_validacion": len(resultado.findings),
            "asserts_crudo": a_crudo,
            "asserts_corregido": a_reparado,
            "errores_assert": errores,
            "trace": resultado.trace.to_dict() if resultado.trace else None,
            "paso": bool(a_reparado)
            and all(e == Resultado.PASA for e in a_reparado.values()),
        }
    )
    return fila


def _evaluar(case: EvalCase, output: dict) -> tuple[dict, dict]:
    """Evalua las aserciones. Devuelve (resultados, errores).

    Una asercion que lanza no se convierte en `False`: se marca ERROR y su motivo
    queda registrado. Un bug nuestro y un fallo del modelo no son lo mismo, y
    `motor.py:409-410` los hacia indistinguibles.
    """
    resultados: dict[str, Resultado] = {}
    errores: dict[str, str] = {}
    for a in case.asserts:
        estado, motivo = a.evaluar(output, case)
        resultados[a.nombre] = estado
        if motivo:
            errores[a.nombre] = motivo
    return resultados, errores


# ---------------------------------------------------------------------------


def run_all(corrida: Corrida, casos: tuple[EvalCase, ...] = EVALS, verbose: bool = True):
    """Corre todos los evals y devuelve (filas, diagnosticos, regresiones, manifiesto)."""
    todas: list[dict] = []
    diagnosticos: list[dict] = []

    for case in casos:
        if verbose:
            print(f"[{corrida.prompt_version}] {case.id} ... ", end="", flush=True)
        filas = correr_eval(case, corrida)
        todas.extend(filas)
        d = diagnosticar(case, filas, n_esperado=corrida.n, umbrales=corrida.umbrales)
        diagnosticos.append(d)
        if verbose:
            errores = f" [{len(d['errores_de_asercion'])} ASERCIONES CON ERROR]" if d[
                "errores_de_asercion"
            ] else ""
            print(f"tasa {d['tasa']}{errores}")

    regresiones = run_regresiones(corrida.rules_version)
    corrida.manifest.finish()
    return todas, diagnosticos, regresiones, corrida.manifest

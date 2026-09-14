"""La CLI del producto: `quickdev analyze`, `quickdev eval` y `quickdev demo`.

Responsabilidad: la superficie de demo. Lee argumentos, arma la composicion
(adaptador, reglas, prompt) y muestra el resultado.

Lo que NO le corresponde: ninguna logica del producto. No valida, no repara, no
arma prompts y no mide: todo eso ya existe en `quickdev/` y en `evals/`, y la CLI
solo lo compone. Si una funcion de aqui empieza a decidir algo sobre el reporte,
esta en el sitio equivocado.

## Por que `demo` nunca llama a la API

`quickdev demo` usa `FakeLlm` sobre `evals/resultados/after/crudo.json`: devuelve
el JSON exacto que el modelo devolvio el dia que se midio `after`, para el lote
normal de 14 comentarios. Es la demo que se puede dar en clase sin wifi, sin API
key y sin cuota, y siempre muestra lo mismo. Todo lo que ocurre despues de la
llamada —parseo, validacion, reparacion, traza— es el codigo de verdad.

Limite: la CLI lee `prompts/`, `evals/` y `docs/ejemplos/` desde la raiz del
repo, asi que funciona con `pip install -e .` (el modo de trabajo del equipo),
no desde un wheel instalado.
"""

import argparse
import json
import sys
from pathlib import Path

from quickdev.adapters import FakeLlm, build_llm
from quickdev.application.analyze_batch import AnalyzeBatch
from quickdev.application.prompting import PromptRegistry
from quickdev.application.types import AnalysisResult
from quickdev.config import Settings
from quickdev.domain.models import PlaytestBatch
from quickdev.domain.rules.registry import rule_set
from quickdev.domain.validation import RepairPolicy, Validator
from quickdev.ports.llm import LlmPort

RAIZ = Path(__file__).resolve().parents[1]
LOTE_DEMO = RAIZ / "docs" / "ejemplos" / "lote_normal.json"
CRUDO_DEMO = RAIZ / "evals" / "resultados" / "after" / "crudo.json"


# ---------------------------------------------------------------------------
# composicion
# ---------------------------------------------------------------------------


def construir_analisis(llm: LlmPort, prompt_version: str, rules_version: str) -> AnalyzeBatch:
    """El caso de uso con sus piezas. La unica composicion de la CLI."""
    settings = Settings(prompt_version=prompt_version, rules_version=rules_version)
    return AnalyzeBatch(
        llm=llm,
        validator=Validator(rule_set(rules_version)),
        repair=RepairPolicy(),
        prompts=PromptRegistry(),
        settings=settings,
    )


def leer_lote(archivo: Path) -> PlaytestBatch:
    """Un lote desde JSON: `{"build": "v0.8.2" | null, "comentarios": [{fuente, texto}]}`."""
    return PlaytestBatch.model_validate_json(Path(archivo).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# presentacion
# ---------------------------------------------------------------------------


def _titulo(texto: str) -> str:
    return f"\n{texto}\n{'-' * len(texto)}"


def formatear(batch: PlaytestBatch, resultado: AnalysisResult) -> str:
    """El resultado en texto legible: lote, reporte, hallazgos, revision humana y traza."""
    r = resultado.report
    lineas = [
        _titulo("Lote de entrada"),
        f"build: {batch.build or 'no especificada'} · {batch.total} comentarios",
        _titulo("Reporte (lo interpreta el modelo)"),
        f"resumen:      {r.resumen_general}",
        f"sentimiento:  {r.sentimiento_general}",
        f"version:      {r.version_juego}",
        f"analizados:   {r.total_comentarios_analizados}",
        "problemas:",
    ]
    for p in r.problemas_detectados:
        lineas.append(f"  [{p.prioridad:5}] {p.categoria:<11} x{p.frecuencia}  {p.descripcion}")
    lineas.append(f"evidencia:    {len(r.comentarios_evidencia)} citas")
    lineas.append("descartados:")
    for d in r.comentarios_descartados:
        lineas.append(f"  ({d.motivo}) {d.texto}")

    lineas.append(_titulo("Hallazgos del validador (lo verifica el codigo)"))
    if resultado.findings:
        for h in resultado.findings:
            lineas.append(f"  {h.rule_id} [{h.field}]: {h.message}")
    else:
        lineas.append("  ninguno: el reporte cumple todas las reglas")

    lineas.append(_titulo("Decision"))
    lineas.append(
        "requiere_revision_humana = "
        f"{r.requiere_revision_humana}"
        + ("  -> una persona revisa antes de actuar" if r.requiere_revision_humana else "")
    )

    if resultado.trace:
        lineas.append(_titulo(f"Traza ({resultado.trace.run_id})"))
        for s in resultado.trace.steps:
            lineas.append(f"  {s.name:<16} {s.decision}")
    return "\n".join(lineas)


def _como_json(resultado: AnalysisResult) -> str:
    return json.dumps(
        {
            "reporte": resultado.report.model_dump(),
            "reporte_crudo": resultado.raw_report,
            "hallazgos": [
                {"rule_id": h.rule_id, "field": h.field, "message": h.message}
                for h in resultado.findings
            ],
            "trace": resultado.trace.to_dict() if resultado.trace else None,
        },
        ensure_ascii=False,
        indent=2,
    )


def _mostrar(batch: PlaytestBatch, resultado: AnalysisResult, como_json: bool) -> None:
    print(_como_json(resultado) if como_json else formatear(batch, resultado))


# ---------------------------------------------------------------------------
# comandos
# ---------------------------------------------------------------------------


def cmd_analyze(args: argparse.Namespace) -> int:
    batch = leer_lote(args.batch)
    registro = PromptRegistry()
    rules_version = args.rules or registro.rules_for(args.prompt)

    if args.replay:
        llm: LlmPort = FakeLlm.from_crudo(args.replay)
    else:
        settings = Settings(prompt_version=args.prompt, rules_version=rules_version)
        if not settings.gemini_api_key:
            print(
                "Falta GEMINI_API_KEY (en .env o en el entorno). Sin clave puedes usar "
                "`quickdev demo`, o `quickdev analyze --replay <crudo.json>` sobre un "
                "lote ya medido.",
                file=sys.stderr,
            )
            return 2
        llm = build_llm(settings)

    resultado = construir_analisis(llm, args.prompt, rules_version).execute(batch)
    _mostrar(batch, resultado, args.json)
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    batch = leer_lote(LOTE_DEMO)
    llm = FakeLlm.from_crudo(CRUDO_DEMO)
    if not args.json:
        print(
            "Demo sin red: la respuesta del modelo es la grabada al medir `after` "
            f"({CRUDO_DEMO.relative_to(RAIZ).as_posix()}). Validacion, reparacion y "
            "traza se ejecutan de verdad."
        )
    resultado = construir_analisis(llm, "after", "after").execute(batch)
    _mostrar(batch, resultado, args.json)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """Delega en el harness de evals. No reimplementa nada."""
    try:
        from evals.__main__ import main as evals_main
    except ImportError:
        print(
            "No encuentro el paquete `evals`. Corre la CLI desde el repo instalado con "
            "`pip install -e .`.",
            file=sys.stderr,
        )
        return 2

    argv = ["--modo", args.prompt]
    if args.rules:
        argv += ["--rules-version", args.rules]
    if args.n is not None:
        argv += ["--n", str(args.n)]
    if args.replay:
        argv += ["--replay", str(args.replay)]
    if args.solo_regresiones:
        argv.append("--solo-regresiones")
    return evals_main(argv)


# ---------------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    versiones = sorted(PromptRegistry().versions)
    p = argparse.ArgumentParser(
        prog="quickdev",
        description="Analiza feedback de playtest: el modelo interpreta, el codigo verifica.",
    )
    sub = p.add_subparsers(dest="comando", required=True)

    a = sub.add_parser("analyze", help="analiza un lote JSON y muestra el reporte")
    a.add_argument("--batch", type=Path, required=True, help="lote JSON")
    a.add_argument("--prompt", default="after", choices=versiones)
    a.add_argument("--rules", default=None, help="por defecto, el que declara el prompt")
    a.add_argument(
        "--replay",
        type=Path,
        default=None,
        metavar="CRUDO_JSON",
        help="reproduce una respuesta ya medida en vez de llamar a la API",
    )
    a.add_argument("--json", action="store_true", help="salida JSON en vez de texto")
    a.set_defaults(func=cmd_analyze)

    e = sub.add_parser("eval", help="corre los evals (delega en python -m evals)")
    e.add_argument("--prompt", default="after", choices=versiones)
    e.add_argument("--rules", default=None, help="por defecto, el que declara el prompt")
    e.add_argument("--n", type=int, default=None)
    e.add_argument("--replay", type=Path, default=None, metavar="CRUDO_JSON")
    e.add_argument("--solo-regresiones", action="store_true")
    e.set_defaults(func=cmd_eval)

    d = sub.add_parser("demo", help="el lote normal de 14 comentarios, sin API key ni red")
    d.add_argument("--json", action="store_true", help="salida JSON en vez de texto")
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

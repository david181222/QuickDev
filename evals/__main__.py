"""Punto de entrada del harness de evals.

    python -m evals --modo baseline --replay evals/resultados/baseline/crudo.json
    python -m evals --modo after --n 10
    python -m evals --solo-regresiones

Reemplaza a `python -m evals.motor`. El flag `--desde-crudo` de aquel se llama
ahora `--replay` y recibe la ruta del archivo, porque ya no es un caso especial
del bucle: es elegir un adaptador (`FakeLlm`) en vez de otro.

Lo que NO hace esta CLI: la del producto. Esa es `quickdev.cli`, de `core/jose`.
Esta es la herramienta de medicion del equipo.
"""

import argparse
import sys
from pathlib import Path

from evals.diagnosis import Umbrales
from evals.prompts_legacy import PROMPT_VERSIONS
from evals.regressions import run_regresiones
from evals.reporting import directorio_de_corrida, escribir_salidas
from evals.runner import construir_corrida, run_all
from quickdev.config import Settings
from quickdev.domain.rules.registry import RULE_SET_VERSIONS


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    p.add_argument("--modo", default="baseline", choices=sorted(PROMPT_VERSIONS))
    p.add_argument(
        "--rules-version",
        default=None,
        choices=sorted(RULE_SET_VERSIONS),
        help="por defecto, el mismo que --modo. Separarlos permite medir un prompt "
        "nuevo con las reglas viejas, que es como se aisla cual de los dos movio el dato.",
    )
    p.add_argument(
        "--n",
        type=int,
        default=None,
        help="corridas por eval. Por defecto, Settings.eval_runs (10). En replay, "
        "por defecto las que haya grabadas.",
    )
    p.add_argument(
        "--replay",
        type=Path,
        default=None,
        metavar="CRUDO_JSON",
        help="reproduce outputs ya medidos en vez de llamar a la API. Sin red y sin cuota.",
    )
    p.add_argument(
        "--solo-regresiones",
        action="store_true",
        help="solo los tests deterministas del validador. Gratis e instantaneo.",
    )
    p.add_argument(
        "--min-corridas-inestabilidad",
        type=int,
        default=Umbrales().min_corridas,
        help="por debajo de este n, la pregunta sobre estabilidad del modelo "
        "responde SIN DATO en vez de inventarse una respuesta.",
    )
    p.add_argument(
        "--fraccion-minima-desviacion",
        type=float,
        default=Umbrales().fraccion_minima,
        help="que fraccion de las corridas debe desviarse para contar como senal.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    rules_version = args.rules_version or args.modo

    if args.solo_regresiones:
        filas = run_regresiones(rules_version)
        ancho = max(len(f["case_id"]) for f in filas)
        for f in filas:
            print(f"{f['pass_fail']:5} {f['case_id']:{ancho}}  {f['expected_check']}")
        pasan = sum(1 for f in filas if f["pass_fail"] == "PASS")
        print(f"\n{pasan}/{len(filas)} PASS con el conjunto de reglas '{rules_version}'")
        return 0

    umbrales = Umbrales(
        min_corridas=args.min_corridas_inestabilidad,
        fraccion_minima=args.fraccion_minima_desviacion,
    )
    settings = Settings(prompt_version=args.modo, rules_version=rules_version)
    corrida = construir_corrida(
        prompt_version=args.modo,
        rules_version=rules_version,
        n=args.n,
        replay=args.replay,
        settings=settings,
        umbrales=umbrales,
    )
    if args.replay:
        print(f"[replay] {args.replay} · n={corrida.n} corridas por eval, sin red")

    filas, diagnosticos, regresiones, manifest = run_all(corrida)
    destino = escribir_salidas(
        directorio_de_corrida(manifest), filas, diagnosticos, regresiones, manifest
    )

    pasan = sum(1 for r in regresiones if r["pass_fail"] == "PASS")
    errores = sum(len(d["errores_de_asercion"]) for d in diagnosticos)
    print(f"\n[{args.modo}] regresiones: {pasan}/{len(regresiones)} PASS")
    if errores:
        print(f"[{args.modo}] AVISO: {errores} aserción(es) lanzaron excepción. Revisalas.")
    print(
        f"\nEscrito en {destino.as_posix()}/: "
        "resultados.csv, diagnostico.md, crudo.json, regresion.csv, manifiesto.json"
    )
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())

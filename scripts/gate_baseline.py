"""Puerta de aceptacion del refactor: el comportamiento medido no cambia.

Compara el resultado de las regresiones deterministas del harness contra el CSV
commiteado en `evals/resultados/baseline/regresion.csv`. Si algo difiere, el
refactor cambio el comportamiento y hay que averiguar por que ANTES de seguir.

No llama al modelo: es determinista, gratis e instantaneo.

Uso:
    ./.venv/Scripts/python.exe scripts/gate_baseline.py

Salida 0 si todo coincide, 1 si algo cambio.

Este script vive en `scripts/` y no en `evals/` a proposito: las tres ramas lo
necesitan, incluida la de Edwin, que mergea antes de que exista el harness nuevo.
Cuando `core/miguel` reescriba `evals/`, la unica linea que hay que actualizar es
el import de `run_regresiones`.

Excepcion prevista: la regla de citas literales se vuelve mas estricta al
corregir el bug de `real in t` (`evals/motor.py:164`). Si eso mueve un caso, va
documentado en el ADR-0003 con el antes y el despues. Cualquier otra diferencia
es una regresion, no una mejora.
"""

import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ESPERADO = RAIZ / "evals" / "resultados" / "baseline" / "regresion.csv"


def main() -> int:
    sys.path.insert(0, str(RAIZ))
    from evals.casos import run_regresiones

    actual = {f["case_id"]: f["pass_fail"] for f in run_regresiones("baseline")}

    if not ESPERADO.is_file():
        print(f"No encuentro la referencia: {ESPERADO}")
        return 1

    with open(ESPERADO, encoding="utf-8") as fh:
        esperado = {r["case_id"]: r["pass_fail"] for r in csv.DictReader(fh)}

    iguales = 0
    for cid, esp in esperado.items():
        act = actual.get(cid, "AUSENTE")
        ok = act == esp
        iguales += ok
        print(f"  {'OK ' if ok else 'DIF'} {cid:<26} commiteado={esp:<5} ahora={act}")

    sobran = sorted(set(actual) - set(esperado))
    if sobran:
        print(f"\n  Casos nuevos, no presentes en la referencia: {sobran}")
        print("  Eso no es un fallo, pero hay que decidir si entran al baseline.")

    total = len(esperado)
    print(f"\n  {iguales}/{total} coinciden con evals/resultados/baseline/regresion.csv")

    if iguales != total:
        print("\n  La puerta esta CERRADA. No 'arregles' el CSV: averigua que cambiaste.")
        return 1

    print("  Puerta ABIERTA: el comportamiento medido no cambio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

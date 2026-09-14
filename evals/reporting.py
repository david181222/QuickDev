"""Los escritores: CSV, JSON y Markdown. Y donde se escriben.

Responsabilidad: convertir el resultado de una corrida en archivos, y elegir el
directorio donde van.

Lo que NO le corresponde: decidir nada sobre el contenido. Si un numero esta mal
aqui, el bug esta en `diagnosis.py`.

## El bug que este modulo existe para no repetir

`motor.py:566` era:

    def carpeta(modo): return DIR / "resultados" / modo

y `escribir_salidas` hacia `to_csv` encima. Es decir: volver a correr los evals
BORRABA la medicion anterior. En un proyecto cuyo objetivo declarado es la
trazabilidad, eso no es un detalle de estilo: significa que el registro historico
dependia de que nadie ejecutara dos veces el mismo comando.

Ahora cada corrida escribe en su propio directorio,
`resultados/<fecha>-<prompt_version>-<rules_version>/`, y si ese nombre ya existe
se le anade un sufijo numerico en vez de pisarlo. `baseline/` y `after/` se
quedan donde estan, intactos, como registro historico. Ver ADR-0007.
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from evals.cases import Resultado
from evals.diagnosis import ERROR_DE_ASERCION, OK
from quickdev.observability.manifest import RunManifest

DIR = Path(__file__).resolve().parent
RESULTADOS = DIR / "resultados"

# Los dos directorios que NO se tocan: son mediciones commiteadas y son la linea
# base contra la que se compara todo lo demas.
HISTORICOS = frozenset({"baseline", "after"})

COLUMNAS_RESULTADOS = (
    "eval_id",
    "categoria",
    "corrida",
    "paso",
    "fallos_validacion",
    "tool_ok",
    "intentos",
    "from_cache",
    "latencia_s",
    "asserts_fallidos_crudo",
    "asserts_fallidos_corregido",
    "asserts_con_error",
    "detalle_validacion",
)


def directorio_de_corrida(manifest: RunManifest, raiz: Path = RESULTADOS) -> Path:
    """El directorio de esta corrida. Nunca uno que ya exista.

    El sufijo numerico no es cosmetico: sin el, dos corridas del mismo dia con
    las mismas versiones colisionarian y volveriamos exactamente al bug de
    sobrescritura que este modulo arregla.
    """
    fecha = (manifest.started_at or datetime.now(UTC).isoformat())[:10]
    base = f"{fecha}-{manifest.prompt_version}-{manifest.rules_version}"
    destino = raiz / base
    n = 2
    while destino.exists():
        destino = raiz / f"{base}-{n}"
        n += 1
    return destino


def escribir_salidas(
    destino: Path,
    filas: list[dict],
    diagnosticos: list[dict],
    regresiones: list[dict],
    manifest: RunManifest,
) -> Path:
    """Escribe los cinco artefactos de una corrida y devuelve el directorio."""
    if destino.name in HISTORICOS:
        raise ValueError(
            f"'{destino.name}' es una medicion commiteada y no se sobrescribe. "
            f"Es el registro historico contra el que se compara el refactor."
        )
    destino.mkdir(parents=True, exist_ok=True)

    _escribir_csv(destino / "resultados.csv", COLUMNAS_RESULTADOS, map(_fila_csv, filas))
    _escribir_crudo(destino / "crudo.json", filas)
    _escribir_csv(
        destino / "regresion.csv",
        tuple(regresiones[0]) if regresiones else (),
        regresiones,
    )
    escribir_diagnostico_md(destino / "diagnostico.md", diagnosticos, regresiones, manifest)
    manifest.write(destino)
    return destino


# ---------------------------------------------------------------------------
# CSV y JSON
# ---------------------------------------------------------------------------


def _nombres(estados: dict, buscado: Resultado) -> str:
    return ";".join(k for k, v in (estados or {}).items() if v == buscado)


def _fila_csv(f: dict) -> dict:
    return {
        "eval_id": f["eval_id"],
        "categoria": f["categoria"],
        "corrida": f["corrida"],
        "paso": f.get("paso"),
        "fallos_validacion": f.get("fallos_validacion"),
        "tool_ok": f.get("tool_ok"),
        "intentos": f.get("intentos"),
        "from_cache": f.get("from_cache"),
        "latencia_s": f.get("latencia_s"),
        "asserts_fallidos_crudo": _nombres(f.get("asserts_crudo"), Resultado.FALLA),
        "asserts_fallidos_corregido": _nombres(f.get("asserts_corregido"), Resultado.FALLA),
        "asserts_con_error": _nombres(f.get("asserts_crudo"), Resultado.ERROR),
        "detalle_validacion": "; ".join((f.get("detalle_hallazgos") or [])[:3]),
    }


def _escribir_csv(archivo: Path, columnas, filas) -> None:
    filas = list(filas)
    if not columnas:
        return
    with open(archivo, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(columnas))
        w.writeheader()
        w.writerows(filas)


def _escribir_crudo(archivo: Path, filas: list[dict]) -> None:
    """El archivo que hace posible el replay. Input y output de cada corrida.

    Se conserva el mismo formato que `baseline/crudo.json` para que `FakeLlm`
    pueda leer indistintamente una medicion vieja y una nueva.
    """
    contenido = {
        f"{f['eval_id']}_run{f['corrida']}": {
            "input": f.get("input"),
            "output_crudo": f.get("output_crudo"),
            "output_corregido": f.get("output_corregido"),
            "fallos_validacion": f.get("detalle_hallazgos"),
            "meta_tool": {
                "tool_ok": f.get("tool_ok"),
                "intentos": f.get("intentos"),
                "truncado": f.get("truncado"),
                "latencia_s": f.get("latencia_s"),
                "from_cache": f.get("from_cache"),
            },
            "trace": f.get("trace"),
        }
        for f in filas
    }
    archivo.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Markdown: el entregable que lee una persona
# ---------------------------------------------------------------------------


def escribir_diagnostico_md(
    archivo: Path,
    diagnosticos: list[dict],
    regresiones: list[dict],
    manifest: RunManifest,
) -> None:
    """Las 7 preguntas respondidas por eval, con su estampado."""
    L = [f"# Diagnóstico de los 5 evals - {manifest.prompt_version}", ""]
    L += _cabecera_manifiesto(manifest)
    L += ["| Eval | Tasa |", "|---|---|"]
    for d in diagnosticos:
        L.append(f"| {d['categoria']} | {d['tasa']} |")
    L.append("")

    for d in diagnosticos:
        L += _bloque_de_eval(d)

    L += _bloque_de_regresiones(regresiones)
    archivo.write_text("\n".join(L), encoding="utf-8")


def _cabecera_manifiesto(manifest: RunManifest) -> list[str]:
    """Sin esto, el archivo no dice que lo produjo y no se puede comparar con otro."""
    m = manifest.to_dict()
    v = m["versiones"]
    return [
        "| | |",
        "|---|---|",
        f"| run_id | `{m['run_id']}` |",
        f"| fecha | {m['started_at']} |",
        f"| prompt / reglas / esquema | `{v['prompt_version']}` / `{v['rules_version']}`"
        f" / `{v['schema_version']}` |",
        f"| modelo | `{v['model']}` |",
        f"| commit | `{v['git_sha']}` |",
        f"| corridas por eval | {m['corridas']} |",
        f"| llamadas (desde caché) | {m['llamadas']['total']} ({m['llamadas']['desde_cache']}) |",
        "",
    ]


def _bloque_de_eval(d: dict) -> list[str]:
    L = [
        f"## {d['categoria']}  (`{d['eval_id']}`)",
        "",
        f"**Tasa:** {d['tasa']} corridas pasadas",
        "",
        f"**Hipótesis:** {d['hipotesis']}",
        "",
    ]

    if not d["corridas_completas"]:
        L += [
            f"> **Aviso:** se pidieron {d['corridas_esperadas']} corridas y hay "
            f"{d['corridas']}. Las tasas de abajo no son comparables con una corrida "
            f"completa.",
            "",
        ]

    if d["errores_de_asercion"]:
        L += [
            f"> **{len(d['errores_de_asercion'])} aserción(es) lanzaron excepción:** "
            f"`{'`, `'.join(d['errores_de_asercion'])}`. Eso es un fallo del eval, no "
            f"del modelo, y no cuenta como hallazgo. Arréglalo antes de leer nada más.",
            "",
        ]

    L += ["| Pregunta | Respuesta | Evidencia |", "|---|---|---|"]
    for pregunta, r in d["preguntas"].items():
        ev = str(r["evidencia"]).replace("|", "\\|")
        if r.get("derivada_de"):
            ev += f" _(derivada de «{r['derivada_de']}», no es una señal independiente)_"
        L.append(f"| {pregunta} | **{r['respuesta']}** | {ev} |")
    L.append("")

    fallidas = {k: v for k, v in d["detalle_asserts"].items() if v["estado"] != OK}
    if fallidas:
        L += [
            "Aserciones que fallaron:",
            "",
            "| Aserción | Causa | Falló en crudo | Sigue fallando | Estado |",
            "|---|---|---|---|---|",
        ]
        for k, v in fallidas.items():
            estado = v["estado"]
            if estado == ERROR_DE_ASERCION:
                estado = f"**{estado}** ({v['errores']} excepción/es)"
            L.append(
                f"| `{k}` | {v['causa']} | {v['fallos_en_crudo']} | "
                f"{v['fallos_tras_validar']} | {estado} |"
            )
        L.append("")

    return L


def _bloque_de_regresiones(regresiones: list[dict]) -> list[str]:
    if not regresiones:
        return []
    L = [
        "## Regresión determinista (reto Core del review)",
        "",
        "Las filas del CSV como tests concretos. No llaman al modelo.",
        "",
        "| case_id | expected_check | resultado |",
        "|---|---|---|",
    ]
    for r in regresiones:
        L.append(f"| {r['case_id']} | {r['expected_check']} | **{r['pass_fail']}** |")
    L.append("")
    return L

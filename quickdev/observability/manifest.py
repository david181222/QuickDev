"""El estampado de una corrida: que la produjo y cuanto costo.

Responsabilidad: reunir, en un solo archivo junto a los resultados, todo lo que
hace falta para saber que produjo esos numeros.

Lo que NO le corresponde: decidir donde se escriben los resultados (eso es
`evals/reporting.py`) ni registrar los pasos de una ejecucion (eso es `Trace`,
que es puro dato y no toca disco).

Por que existe, en una frase: sin este estampado, comparar `baseline/` con
`after/` es un acto de fe. Los dos directorios contienen numeros y ninguno de los
dos archivos dice con que prompt, con que reglas, con que modelo ni sobre que
commit se midieron. Este modulo es lo unico del repo que averigua el `git_sha`, y
por eso es tambien lo unico que hace `subprocess`.
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from quickdev.ports.llm import LlmResponse

RAIZ = Path(__file__).resolve().parent.parent.parent

NOMBRE_ARCHIVO = "manifiesto.json"


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _git(*args: str, raiz: Path | None = None) -> str | None:
    """Corre un comando de git y devuelve su salida, o None si no se puede."""
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=raiz or RAIZ,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def git_sha(raiz: Path | None = None) -> str:
    """El commit sobre el que se midio.

    Si el arbol tiene cambios sin commitear, el sha lleva el sufijo `-sucio`. Eso
    no es cosmetico: una medicion tomada sobre codigo que no esta en ningun
    commit no se puede reproducir, y el archivo tiene que decirlo en vez de
    aparentar que si. Si git no esta disponible, devuelve "desconocido" en vez de
    reventar: un manifiesto incompleto sigue siendo mejor que una corrida sin
    manifiesto.
    """
    sha = _git("rev-parse", "--short", "HEAD", raiz=raiz)
    if not sha:
        return "desconocido"
    sucio = _git("status", "--porcelain", raiz=raiz)
    return f"{sha}-sucio" if sucio else sha


@dataclass
class RunManifest:
    """Lo que identifica una corrida de evals, mas lo que costo producirla.

    Las cinco versiones (`prompt_version`, `rules_version`, `schema_version`,
    `model`, `git_sha`) son las que hacen comparables dos mediciones. Los
    agregados de abajo son los que permiten discutir si una corrida fue cara o
    lenta con un dato en vez de con una impresion.

    Sobre el coste en dinero: se agregan tokens, no euros. El repo no tiene tabla
    de precios y meter una constante inventada en un archivo de trazabilidad es
    peor que no ponerla. Queda anotado como pendiente en la seccion 8 del plan.
    """

    prompt_version: str
    rules_version: str
    schema_version: str
    model: str
    n_corridas: int = 0
    run_id: str = field(default_factory=lambda: uuid4().hex[:12])
    started_at: str = field(default_factory=_ahora_iso)
    finished_at: str = ""
    git_sha: str = field(default_factory=git_sha)

    # --- agregados de la capa de llamada -----------------------------------
    llamadas: int = 0
    llamadas_cacheadas: int = 0
    intentos_totales: int = 0
    errores: int = 0
    latencias_s: list[float] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    notas: dict = field(default_factory=dict)

    # -- registro -----------------------------------------------------------

    def record_call(self, respuesta: LlmResponse) -> None:
        """Contabiliza una llamada al modelo.

        Las llamadas servidas por cache NO entran en las latencias: mezclarlas
        con las reales haria que subir el numero de corridas pareciera acelerar
        el modelo. Se cuentan aparte, que es la informacion util.
        """
        self.llamadas += 1
        self.intentos_totales += respuesta.attempts
        if respuesta.from_cache:
            self.llamadas_cacheadas += 1
        else:
            self.latencias_s.append(round(respuesta.latency_s, 3))
        for clave, valor in (respuesta.usage or {}).items():
            if isinstance(valor, int):
                self.tokens[clave] = self.tokens.get(clave, 0) + valor

    def record_error(self, exc: BaseException) -> None:
        """Contabiliza una llamada que murio. Un eval con errores no es un eval limpio."""
        self.errores += 1
        detalle = self.notas.setdefault("errores", [])
        detalle.append(f"{type(exc).__name__}: {str(exc)[:200]}")

    def finish(self) -> "RunManifest":
        """Cierra la corrida. Devuelve self para poder encadenar con `write`."""
        self.finished_at = _ahora_iso()
        return self

    # -- salida -------------------------------------------------------------

    @property
    def latencia_total_s(self) -> float:
        return round(sum(self.latencias_s), 2)

    @property
    def latencia_media_s(self) -> float:
        if not self.latencias_s:
            return 0.0
        return round(sum(self.latencias_s) / len(self.latencias_s), 2)

    @property
    def tasa_de_cache(self) -> float:
        """Que fraccion de las llamadas no gasto cuota."""
        if not self.llamadas:
            return 0.0
        return round(self.llamadas_cacheadas / self.llamadas, 3)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "versiones": {
                "prompt_version": self.prompt_version,
                "rules_version": self.rules_version,
                "schema_version": self.schema_version,
                "model": self.model,
                "git_sha": self.git_sha,
            },
            "corridas": self.n_corridas,
            "llamadas": {
                "total": self.llamadas,
                "desde_cache": self.llamadas_cacheadas,
                "tasa_de_cache": self.tasa_de_cache,
                "intentos_totales": self.intentos_totales,
                "errores": self.errores,
            },
            "latencia": {
                "total_s": self.latencia_total_s,
                "media_s": self.latencia_media_s,
                "muestras": len(self.latencias_s),
            },
            "tokens": dict(sorted(self.tokens.items())),
            "notas": self.notas,
        }

    def write(self, destino: Path) -> Path:
        """Escribe `manifiesto.json` en el directorio de la corrida."""
        destino.mkdir(parents=True, exist_ok=True)
        archivo = destino / NOMBRE_ARCHIVO
        archivo.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return archivo

"""Configuracion de QuickDev, en un solo lugar.

Responsabilidad: reunir los valores que hoy son numeros magicos repartidos entre
el notebook y `evals/motor.py` (`MODEL = "gemini-2.5-flash"` en dos sitios,
`temperature=0`, `max_output_tokens=6144`, `retries=3`, el backoff de 45
segundos).

`core/edwin` refina este modulo: propiedades derivadas y la validacion de que la
combinacion de versiones existe. Los campos y sus defaults son definitivos.
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from quickdev.domain.rules.registry import RULE_SET_VERSIONS

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Los parametros de una corrida.

    Se leen del `.env` de la raiz del repo, sin prefijo y sin distinguir
    mayusculas: el `GEMINI_API_KEY` que el equipo ya tiene en su `.env` resuelve
    a `gemini_api_key` sin tocar nada. No ponemos `env_prefix` justamente para
    no romper ese archivo, que no esta versionado y que cada uno tiene local.
    """

    model_config = SettingsConfigDict(
        env_file=RAIZ / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- proveedor ---------------------------------------------------------
    gemini_api_key: str = ""
    model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    max_output_tokens: int = 6144

    # --- capa de llamada ---------------------------------------------------
    retries: int = 3
    backoff_base_s: float = 5.0
    cache_dir: Path = RAIZ / ".cache" / "llm"
    cache_enabled: bool = True

    # --- versiones que se estampan en cada corrida -------------------------
    # Sin este estampado, dos carpetas de resultados no son comparables.
    prompt_version: str = "after"
    rules_version: str = "after"

    # --- flujo -------------------------------------------------------------
    # Apagada a proposito: se enciende cuando una medicion de pass@1 contra
    # pass@2 la justifique. Ver ADR-0004.
    repair_round_enabled: bool = False

    # --- evals -------------------------------------------------------------
    # 10 y no 3: con n=3 no se distingue un flake de un defecto, y esa era la
    # base sobre la que el diagnostico respondia "elegimos mal el modelo?".
    # Con cache en disco, subir n es casi gratis.
    eval_runs: int = 10

    # -----------------------------------------------------------------------

    @field_validator("rules_version")
    @classmethod
    def _conjunto_de_reglas_existente(cls, valor: str) -> str:
        """Un conjunto de reglas inexistente falla al arrancar, no a mitad de corrida.

        Sin esto, un `rules_version` mal escrito revienta con un KeyError dentro
        del bucle de evals, despues de haber gastado llamadas a la API.
        """
        if valor not in RULE_SET_VERSIONS:
            raise ValueError(
                f"conjunto de reglas '{valor}' inexistente. "
                f"Disponibles: {sorted(RULE_SET_VERSIONS)}"
            )
        return valor

    # `prompt_version` NO se valida aqui, a proposito. Hacerlo obligaria a
    # `config.py` a importar `application.prompting`, que es una capa que ya
    # depende de `config`. Y no hace falta para lo que protegia el validador de
    # reglas: una version de prompt inexistente revienta con KeyError en
    # `render_prompt`, el PRIMER paso de AnalyzeBatch, antes de cualquier llamada
    # a la API. La CLI de evals, ademas, la restringe con `choices`.

    @property
    def stamp(self) -> dict[str, str]:
        """Lo que identifica una corrida. Sin esto, dos mediciones no se comparan."""
        return {
            "model": self.model,
            "prompt_version": self.prompt_version,
            "rules_version": self.rules_version,
        }

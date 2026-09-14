"""Fixtures de los tests de adaptadores.

Los dobles viven en `dobles.py`; aqui solo las fixtures que los sirven. Hereda
ademas las de `tests/conftest.py`. Ver `__init__.py` sobre por que esta carpeta
es un paquete.
"""

import pytest

from quickdev.config import Settings
from quickdev.ports.llm import LlmRequest

from .dobles import RelojFalso


@pytest.fixture
def peticion() -> LlmRequest:
    return LlmRequest(system_prompt="eres un analizador", payload={"input": "lote de prueba"})


@pytest.fixture
def settings_sin_red(tmp_path) -> Settings:
    """Settings que no leen el `.env` real, para que el test no dependa de la maquina."""
    return Settings(
        _env_file=None,
        gemini_api_key="clave-de-prueba",
        cache_dir=tmp_path / "cache",
        model="modelo-de-prueba",
    )


@pytest.fixture
def reloj() -> RelojFalso:
    return RelojFalso()

"""La interfaz web compone el producto sin anadirle logica.

Corren sin red y sin API key: el modo demo usa `FakeLlm` sobre las mediciones
commiteadas. Se saltan si Streamlit no esta instalado (es el extra `web`).
"""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

from evals.cases import EVALS
from quickdev.adapters import SinRespuestaGrabada
from quickdev.domain.models import PlaytestBatch, PlaytestComment
from quickdev.web import app as web

APP = Path(web.__file__)


@pytest.fixture(autouse=True)
def sin_api_key(monkeypatch):
    """Una variable de entorno vacia gana al `.env` local de quien corra los tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "")


@pytest.fixture
def app() -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    assert not at.exception
    return at


def _textos(at: AppTest) -> str:
    partes = [*at.markdown, *at.warning, *at.success, *at.caption, *at.info]
    return "\n".join(str(p.value) for p in partes)


def _analizar(at: AppTest) -> dict[str, str]:
    boton = next(b for b in at.button if b.label == "🔍 Analizar")
    boton.click().run()
    assert not at.exception
    return {m.label: m.value for m in at.metric}


def test_arranca_con_el_ejemplo_normal_y_sin_reporte(app):
    assert "14 comentarios" in _textos(app)
    assert not app.metric  # todavia no se analizo nada


def test_analizar_el_ejemplo_normal_en_demo(app):
    metricas = _analizar(app)
    assert metricas["Comentarios"] == "14"
    assert metricas["Versión"] == "v0.8.2"
    assert "Requiere revisión humana" in _textos(app)


def test_el_edge_case_de_version_reporta_la_build_analizada(app):
    edge = next(c for c in EVALS if c.id == "edge_case_version_conflictiva")
    ejemplo = next(s for s in app.selectbox if s.label == "Ejemplo")
    ejemplo.set_value(edge).run()
    assert _analizar(app)["Versión"] == edge.batch.build


def test_baseline_tambien_tiene_demo(app):
    prompt = next(s for s in app.sidebar.selectbox if s.label == "Versión del prompt")
    prompt.set_value("baseline").run()
    assert _analizar(app)["Comentarios"] == "14"


def test_v2_no_tiene_respuestas_grabadas_y_no_deja_analizar(app):
    prompt = next(s for s in app.sidebar.selectbox if s.label == "Versión del prompt")
    prompt.set_value("v2").run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "🔍 Analizar").disabled
    assert "no tiene respuestas grabadas" in _textos(app)


def test_el_lote_manual_vacio_no_se_puede_analizar(app):
    app.button_group[0].set_value("✍️ Escribir comentarios").run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "🔍 Analizar").disabled
    assert "Escribe al menos un comentario" in _textos(app)


def test_en_vivo_sin_clave_no_deja_analizar(app):
    app.sidebar.radio[0].set_value(web.VIVO).run()
    assert not app.exception
    assert next(b for b in app.button if b.label == "🔍 Analizar").disabled


def test_un_lote_sin_grabar_no_tiene_respuesta_en_demo():
    """La app atrapa esto y muestra un aviso; aqui se comprueba que la causa es esa."""
    lote = PlaytestBatch(
        build="v1.0", comentarios=[PlaytestComment(fuente="discord", texto="Muy divertido")]
    )
    with pytest.raises(SinRespuestaGrabada):
        web.analizar(lote, web.DEMO, "after", api_key="")

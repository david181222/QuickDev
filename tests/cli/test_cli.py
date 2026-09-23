"""La CLI compone el producto sin anadirle logica.

Todos estos tests corren sin red y sin API key: la demo y el replay usan
`FakeLlm` sobre las mediciones commiteadas.
"""

import json
from pathlib import Path

import pytest

from evals.cases import LOTE_NORMAL
from quickdev import cli
from quickdev.adapters import SinRespuestaGrabada

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def sin_api_key(monkeypatch):
    """Una variable de entorno vacia gana al `.env` local de quien corra los tests."""
    monkeypatch.setenv("GEMINI_API_KEY", "")


def test_el_lote_de_la_demo_es_el_lote_normal_medido():
    """Si alguien edita uno y no el otro, la demo dejaria de encontrar su respuesta."""
    assert cli.leer_lote(cli.LOTE_DEMO) == LOTE_NORMAL


def test_demo_funciona_sin_api_key(capsys):
    assert cli.main(["demo"]) == 0
    salida = capsys.readouterr().out
    assert "14 comentarios" in salida
    assert "requiere_revision_humana = True" in salida
    assert "render_prompt" in salida and "repair_or_retry" in salida


def test_demo_en_json_es_json_valido(capsys):
    assert cli.main(["demo", "--json"]) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["reporte"]["total_comentarios_analizados"] == 14
    assert datos["trace"]["prompt_version"] == "after"


def test_analyze_con_replay(capsys):
    codigo = cli.main(
        ["analyze", "--batch", str(cli.LOTE_DEMO), "--replay", str(cli.CRUDO_DEMO), "--json"]
    )
    assert codigo == 0
    assert json.loads(capsys.readouterr().out)["reporte"]["version_juego"] == "v0.8.2"


def test_analyze_sin_clave_ni_replay_explica_la_salida(capsys):
    assert cli.main(["analyze", "--batch", str(cli.LOTE_DEMO)]) == 2
    assert "quickdev demo" in capsys.readouterr().err


def test_analyze_con_un_prompt_sin_grabar_falla_ruidoso():
    with pytest.raises(SinRespuestaGrabada):
        cli.main(
            [
                "analyze",
                "--batch",
                str(cli.LOTE_DEMO),
                "--prompt",
                "v2",
                "--replay",
                str(cli.CRUDO_DEMO),
            ]
        )


def test_eval_delega_en_el_harness(capsys):
    assert cli.main(["eval", "--prompt", "baseline", "--solo-regresiones"]) == 0
    assert "5/7 PASS" in capsys.readouterr().out

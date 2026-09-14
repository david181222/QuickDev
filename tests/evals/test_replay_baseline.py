"""La puerta final de la migracion, como test: el replay reproduce lo medido.

Corre el pipeline COMPLETO -prompt, llamada, parseo, validacion, reparacion,
aserciones, diagnostico- sobre las 30 corridas guardadas en
`evals/resultados/*/crudo.json`, con `FakeLlm` en lugar del proveedor. Sin red,
sin API key, sin cuota y determinista.

Esto es el pago inmediato de la arquitectura hexagonal, y por eso vive en la
suite y no en un comando que alguien recuerda correr: si el refactor cambia el
comportamiento medido, sale rojo en el siguiente `pytest`.

## Que se compara, y que no

Se compara el COMPORTAMIENTO OBSERVADO: la tasa de cada eval y, asercion por
asercion, cuantas veces fallo en crudo y cuantas siguio fallando tras el
validador. Eso tiene que ser identico a lo commiteado.

Lo que SI cambia deliberadamente son tres respuestas DERIVADAS de ese
comportamiento, porque tres inferencias del diagnostico viejo estaban mal. El
antes y el despues de cada una esta en el ADR-0008, y los tests de abajo las
fijan para que el cambio sea intencionado y no un accidente.
"""

import re
from pathlib import Path

import pytest

from evals.cases import EVALS, POR_ID, Resultado
from evals.diagnosis import Respuesta
from evals.runner import construir_corrida, run_all

RESULTADOS = Path(__file__).resolve().parents[2] / "evals" / "resultados"

# Lo commiteado, parseado del diagnostico que ya esta en el repo. No se copia a
# mano: si alguien edita el archivo, este test lo ve.
FILA_ASERCION = re.compile(
    r"^\| `(?P<nombre>[^`]+)` \| (?P<causa>[^|]+) \| (?P<crudo>\S+) \| (?P<tras>\S+) \| "
    r"(?P<estado>[^|]+) \|$"
)
FILA_TASA = re.compile(r"^\| (?P<categoria>\d\. [^|]+?) \| (?P<tasa>\d+/\d+) \|$")


def leer_commiteado(modo: str) -> tuple[dict, dict]:
    """(tasas por categoria, aserciones fallidas por nombre) del diagnostico guardado."""
    texto = (RESULTADOS / modo / "diagnostico.md").read_text(encoding="utf-8")
    tasas, aserciones = {}, {}
    for linea in texto.splitlines():
        if m := FILA_TASA.match(linea):
            tasas[m["categoria"].strip()] = m["tasa"]
        elif m := FILA_ASERCION.match(linea):
            aserciones[m["nombre"]] = {
                "crudo": m["crudo"],
                "tras": m["tras"],
                "estado": m["estado"].strip(),
            }
    return tasas, aserciones


@pytest.fixture(scope="module")
def replay_baseline():
    corrida = construir_corrida(
        prompt_version="baseline",
        rules_version="baseline",
        replay=RESULTADOS / "baseline" / "crudo.json",
    )
    filas, diagnosticos, regresiones, manifest = run_all(corrida, verbose=False)
    return {
        "filas": filas,
        "diagnosticos": {d["eval_id"]: d for d in diagnosticos},
        "regresiones": regresiones,
        "manifest": manifest,
    }


# ---------------------------------------------------------------------------
# Lo que TIENE que reproducirse
# ---------------------------------------------------------------------------


def test_reproduce_las_tasas_commiteadas(replay_baseline):
    tasas_commiteadas, _ = leer_commiteado("baseline")

    ahora = {d["categoria"]: d["tasa"] for d in replay_baseline["diagnosticos"].values()}

    assert ahora == tasas_commiteadas


def test_reproduce_cada_asercion_fallida(replay_baseline):
    """Asercion por asercion: cuantas veces fallo en crudo y cuantas tras validar.

    Este es el test que sostiene el refactor completo. Si una regla cambio de
    comportamiento, aqui se ve exactamente cual.
    """
    _, commiteadas = leer_commiteado("baseline")

    ahora = {}
    for d in replay_baseline["diagnosticos"].values():
        for nombre, v in d["detalle_asserts"].items():
            if v["estado"] != "ok":
                ahora[nombre] = {
                    "crudo": v["fallos_en_crudo"],
                    "tras": v["fallos_tras_validar"],
                    "estado": v["estado"],
                }

    assert ahora == commiteadas


def test_las_regresiones_siguen_dando_lo_mismo(replay_baseline):
    resultados = {r["case_id"]: r["pass_fail"] for r in replay_baseline["regresiones"]}

    assert resultados == {
        "happy_path": "PASS",
        "missing_version": "PASS",
        "frequency_overflow": "PASS",
        "non_literal_evidence": "PASS",
        "discarded_bias": "PASS",
        # Los dos FAIL deliberados: exponen el falso positivo del validador
        # baseline y el edge case que no podia atrapar.
        "version_ausente_legitima": "FAIL",
        "version_de_otro_build": "FAIL",
    }


def test_ninguna_asercion_revienta(replay_baseline):
    """Si esto falla, hay un bug en un eval, no un hallazgo sobre el modelo."""
    con_error = {
        d["eval_id"]: d["errores_de_asercion"]
        for d in replay_baseline["diagnosticos"].values()
        if d["errores_de_asercion"]
    }

    assert con_error == {}


def test_las_quince_corridas_estan_completas(replay_baseline):
    assert len(replay_baseline["filas"]) == 15
    assert all(d["corridas_completas"] for d in replay_baseline["diagnosticos"].values())


# ---------------------------------------------------------------------------
# Lo que cambia a proposito. ADR-0008.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "eval_id", ["happy_path", "input_ambiguo", "input_adversarial"]
)
def test_la_tool_deja_de_reportarse_como_fallida_por_un_reintento(replay_baseline, eval_id):
    """Antes: SÍ, "falló o reintentó en 1/3 corridas" en un eval que salio 3/3."""
    d = replay_baseline["diagnosticos"][eval_id]

    assert d["preguntas"]["¿La tool devolvió mal?"]["respuesta"] == str(Respuesta.NO)


def test_la_pregunta_del_modelo_pasa_a_sin_dato_con_n_igual_a_3(replay_baseline):
    """Antes: SÍ o NO segun `0 < fallos < 3`. Tres corridas no dan para eso."""
    respuestas = {
        d["preguntas"]["¿Elegimos mal el modelo?"]["respuesta"]
        for d in replay_baseline["diagnosticos"].values()
    }

    assert respuestas == {str(Respuesta.SIN_DATO)}


def test_la_pregunta_de_contexto_se_declara_derivada(replay_baseline):
    for d in replay_baseline["diagnosticos"].values():
        assert d["preguntas"]["¿Faltó contexto?"]["derivada_de"] == "¿Falló el prompt?"


# ---------------------------------------------------------------------------
# El replay no toca nada
# ---------------------------------------------------------------------------


def test_el_replay_no_llama_a_la_api(replay_baseline):
    m = replay_baseline["manifest"].to_dict()

    assert m["versiones"]["model"] == "replay"
    assert m["llamadas"]["errores"] == 0
    assert m["llamadas"]["total"] == 15


def test_el_edge_case_sigue_siendo_el_que_falla(replay_baseline):
    """0/3 en el baseline: es el caso que motivo el prompt `after`."""
    d = replay_baseline["diagnosticos"]["edge_case_version_conflictiva"]

    assert d["tasa"] == "0/3"
    assert d["preguntas"]["¿Faltó validación?"]["respuesta"] == str(Respuesta.SI)


# ---------------------------------------------------------------------------
# El modo after, tambien
# ---------------------------------------------------------------------------


def test_el_after_reproduce_su_quince_de_quince():
    """La medicion `after` fue 15/15. Si el refactor la movio, se ve aqui."""
    corrida = construir_corrida(
        prompt_version="after",
        rules_version="after",
        replay=RESULTADOS / "after" / "crudo.json",
    )
    _, diagnosticos, _, _ = run_all(corrida, verbose=False)

    assert [d["tasa"] for d in diagnosticos] == ["3/3"] * 5


def test_todos_los_evals_tienen_caso_y_aserciones():
    assert len(EVALS) == 5
    assert set(POR_ID) == {c.id for c in EVALS}
    assert all(c.asserts for c in EVALS)


def test_las_aserciones_devuelven_el_enum_no_un_bool():
    """El tercer estado solo existe si nadie lo colapsa a bool por el camino."""
    caso = POR_ID["happy_path"]
    estado, motivo = caso.asserts[0].evaluar({}, caso)

    assert estado is Resultado.FALLA
    assert motivo == ""

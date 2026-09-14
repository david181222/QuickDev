"""Las seis inferencias que se arreglaron, una por una.

Cada test nombra la linea de `motor.py` que derivaba mal, para que el dia que
alguien "simplifique" esto sepa que esta deshaciendo. Ver ADR-0008.
"""

import pytest

from evals.cases import POR_ID, Resultado
from evals.diagnosis import (
    ERROR_DE_ASERCION,
    Respuesta,
    Umbrales,
    diagnosticar,
)

CASO = POR_ID["happy_path"]
PREGUNTA_TOOL = "¿La tool devolvió mal?"
PREGUNTA_MODELO = "¿Elegimos mal el modelo?"
PREGUNTA_CONTEXTO = "¿Faltó contexto?"
PREGUNTA_PROMPT = "¿Falló el prompt?"


def fila(corrida: int, *, estados=None, intentos=1, tool_ok=True, truncado=False, paso=True):
    """Una fila de corrida, con todas las aserciones pasando salvo lo que se diga."""
    base = {a.nombre: Resultado.PASA for a in CASO.asserts}
    base.update(estados or {})
    return {
        "eval_id": CASO.id,
        "categoria": CASO.categoria,
        "corrida": corrida,
        "tool_ok": tool_ok,
        "intentos": intentos,
        "truncado": truncado,
        "asserts_crudo": base,
        "asserts_corregido": dict(base),
        "paso": paso,
    }


def respuesta(d, pregunta):
    return d["preguntas"][pregunta]["respuesta"]


# ---------------------------------------------------------------------------
# 1. motor.py:374 - reintentar no es fallar
# ---------------------------------------------------------------------------


def test_un_reintento_ya_no_marca_la_tool_como_fallida():
    """El caso real del baseline: happy path 3/3 reportado como fallo de la tool."""
    filas = [fila(1, intentos=2), fila(2), fila(3)]

    d = diagnosticar(CASO, filas, n_esperado=3)

    assert respuesta(d, PREGUNTA_TOOL) == str(Respuesta.NO)
    assert "1 reintento(s), que no cuentan como fallo" in d["preguntas"][PREGUNTA_TOOL]["evidencia"]


@pytest.mark.parametrize(
    ("kwargs", "esperado"),
    [
        ({"tool_ok": False}, Respuesta.SI),
        ({"truncado": True}, Respuesta.SI),
        ({"intentos": 3}, Respuesta.NO),
    ],
)
def test_la_tool_falla_solo_si_murio_o_se_trunco(kwargs, esperado):
    d = diagnosticar(CASO, [fila(1, **kwargs)], n_esperado=1)

    assert respuesta(d, PREGUNTA_TOOL) == str(esperado)


# ---------------------------------------------------------------------------
# 2. motor.py:500 - el umbral de inestabilidad
# ---------------------------------------------------------------------------


def test_con_pocas_corridas_la_pregunta_del_modelo_no_se_responde():
    """`0 < fallos < 3` llamaba inestable a un unico fallo de tres corridas."""
    filas = [fila(1, estados={"hitl_marcado": Resultado.FALLA}), fila(2), fila(3)]

    d = diagnosticar(CASO, filas, n_esperado=3)

    assert respuesta(d, PREGUNTA_MODELO) == str(Respuesta.SIN_DATO)
    assert "no bastan para separar un flake de un defecto" in (
        d["preguntas"][PREGUNTA_MODELO]["evidencia"]
    )


def test_un_solo_fallo_en_diez_corridas_es_ruido_no_senal():
    filas = [fila(1, estados={"hitl_marcado": Resultado.FALLA})] + [
        fila(i) for i in range(2, 11)
    ]

    d = diagnosticar(CASO, filas, n_esperado=10)

    assert respuesta(d, PREGUNTA_MODELO) == str(Respuesta.NO)


def test_dos_fallos_en_diez_ya_superan_el_umbral():
    filas = [
        fila(1, estados={"hitl_marcado": Resultado.FALLA}),
        fila(2, estados={"hitl_marcado": Resultado.FALLA}),
    ] + [fila(i) for i in range(3, 11)]

    d = diagnosticar(CASO, filas, n_esperado=10)

    assert respuesta(d, PREGUNTA_MODELO) == str(Respuesta.SI)
    assert "hitl_marcado" in d["preguntas"][PREGUNTA_MODELO]["evidencia"]


def test_fallar_siempre_no_es_inestabilidad_es_un_defecto():
    """Si falla en 10/10 no es varianza del modelo: es que la instruccion no esta."""
    filas = [fila(i, estados={"hitl_marcado": Resultado.FALLA}) for i in range(1, 11)]

    d = diagnosticar(CASO, filas, n_esperado=10)

    assert respuesta(d, PREGUNTA_MODELO) == str(Respuesta.NO)
    assert respuesta(d, PREGUNTA_CONTEXTO) == str(Respuesta.SI)


def test_el_umbral_es_configurable():
    filas = [fila(1, estados={"hitl_marcado": Resultado.FALLA})] + [
        fila(i) for i in range(2, 11)
    ]

    umbrales = Umbrales(min_corridas=3, fraccion_minima=0.05)
    estricto = diagnosticar(CASO, filas, 10, umbrales=umbrales)

    assert respuesta(estricto, PREGUNTA_MODELO) == str(Respuesta.SI)


# ---------------------------------------------------------------------------
# 3. motor.py:512 - contexto no es independiente del prompt
# ---------------------------------------------------------------------------


def test_la_pregunta_de_contexto_se_declara_derivada():
    d = diagnosticar(CASO, [fila(1)], n_esperado=1)

    assert d["preguntas"][PREGUNTA_CONTEXTO]["derivada_de"] == PREGUNTA_PROMPT


def test_contexto_nunca_da_si_si_el_prompt_da_no():
    """La relacion que motor.py ocultaba, escrita como test."""
    filas = [fila(i) for i in range(1, 4)]

    d = diagnosticar(CASO, filas, n_esperado=3)

    assert respuesta(d, PREGUNTA_PROMPT) == str(Respuesta.NO)
    assert respuesta(d, PREGUNTA_CONTEXTO) == str(Respuesta.NO)


# ---------------------------------------------------------------------------
# 4. motor.py:409-410 - el tercer estado
# ---------------------------------------------------------------------------


def test_una_asercion_que_revienta_no_se_cuenta_como_fallo_del_modelo():
    filas = [fila(1, estados={"citas_literales": Resultado.ERROR})]

    d = diagnosticar(CASO, filas, n_esperado=1)

    assert d["errores_de_asercion"] == ["citas_literales"]
    assert d["detalle_asserts"]["citas_literales"]["estado"] == ERROR_DE_ASERCION
    # Y no contamina la pregunta del prompt: no es un hallazgo sobre el modelo.
    assert respuesta(d, PREGUNTA_PROMPT) == str(Respuesta.NO)


# ---------------------------------------------------------------------------
# 5. motor.py:429-431 - n no se encoge en silencio
# ---------------------------------------------------------------------------


def test_una_corrida_incompleta_se_declara():
    d = diagnosticar(CASO, [fila(1), fila(2)], n_esperado=3)

    assert d["corridas"] == 2
    assert d["corridas_esperadas"] == 3
    assert d["corridas_completas"] is False


def test_una_corrida_completa_tambien_se_declara():
    d = diagnosticar(CASO, [fila(i) for i in (1, 2, 3)], n_esperado=3)

    assert d["corridas_completas"] is True


# ---------------------------------------------------------------------------
# 6. Lo que NO cambio: la distincion crudo / corregido
# ---------------------------------------------------------------------------


def test_salvado_por_codigo_y_no_detectado_siguen_siendo_distintos():
    """Lo mejor del harness viejo: evaluar dos veces separa dos diagnosticos."""
    salvado = fila(1, estados={"total_correcto": Resultado.FALLA})
    salvado["asserts_corregido"]["total_correcto"] = Resultado.PASA

    no_detectado = fila(2, estados={"citas_literales": Resultado.FALLA})
    no_detectado["asserts_corregido"]["citas_literales"] = Resultado.FALLA

    d = diagnosticar(CASO, [salvado, no_detectado], n_esperado=2)

    assert d["detalle_asserts"]["total_correcto"]["estado"] == "salvado_por_codigo"
    assert d["detalle_asserts"]["citas_literales"]["estado"] == "no_detectado"
    assert respuesta(d, "¿Faltó validación?") == str(Respuesta.SI)

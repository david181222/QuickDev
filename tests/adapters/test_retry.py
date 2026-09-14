"""La politica de reintentos. Sin red y sin dormir de verdad.

Los dos comportamientos que este archivo existe para fijar son los dos defectos
concretos del harness viejo: dormir ante un error que no se va a arreglar, y
confundir "reintento" con "fallo".
"""

import pytest

from quickdev.adapters.retry import RetryingLlm
from quickdev.ports.llm import (
    LlmResponse,
    LlmRetryableError,
    LlmTerminalError,
)

from .dobles import REPORTE_VALIDO, ContadorLlm


def respuesta_ok() -> LlmResponse:
    return LlmResponse(data=REPORTE_VALIDO, raw_text="{}", model="doble")


# ---------------------------------------------------------------------------
# Lo reintentable
# ---------------------------------------------------------------------------


def test_sin_error_no_reintenta(peticion, reloj):
    inner = ContadorLlm()
    r = RetryingLlm(inner, retries=3, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 1
    assert r.attempts == 1
    assert reloj.esperas == []


def test_reintenta_lo_transitorio_y_devuelve_el_exito(peticion, reloj):
    inner = ContadorLlm([LlmRetryableError("429"), respuesta_ok()])

    r = RetryingLlm(inner, retries=3, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 2
    assert r.data == REPORTE_VALIDO


def test_reintentar_no_es_fallar(peticion, reloj):
    """El defecto de motor.py:374, dicho como test.

    Un happy path que salio bien al segundo intento es un happy path. La
    respuesta lleva `attempts=2` como dato, y no hay ningun campo que diga que
    la tool fallo, porque no fallo.
    """
    inner = ContadorLlm([LlmRetryableError("rate limit"), respuesta_ok()])

    r = RetryingLlm(inner, retries=3, sleep=reloj).complete_json(peticion)

    assert r.attempts == 2
    assert r.data == REPORTE_VALIDO


def test_el_backoff_crece_al_doble(peticion, reloj):
    inner = ContadorLlm(
        [LlmRetryableError("1"), LlmRetryableError("2"), respuesta_ok()]
    )

    RetryingLlm(inner, retries=3, backoff_base_s=5.0, sleep=reloj).complete_json(peticion)

    assert reloj.esperas == [5.0, 10.0]


def test_agotar_los_intentos_lanza_el_ultimo_error(peticion, reloj):
    inner = ContadorLlm([LlmRetryableError("uno"), LlmRetryableError("dos")])

    with pytest.raises(LlmRetryableError, match="Agotados los 2 intentos"):
        RetryingLlm(inner, retries=2, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 2
    # Dos intentos, UNA espera: no se duerme despues del ultimo.
    assert len(reloj.esperas) == 1


# ---------------------------------------------------------------------------
# Lo terminal: el bug de los 135 segundos
# ---------------------------------------------------------------------------


def test_un_error_terminal_se_propaga_sin_dormir(peticion, reloj):
    """Con una API key invalida, motor.py:383-389 dormia 45+90 = 135 segundos.

    Aqui se propaga al primer intento y el reloj no registra ni una espera.
    """
    inner = ContadorLlm([LlmTerminalError("401: api key invalida")])

    with pytest.raises(LlmTerminalError, match="401"):
        RetryingLlm(inner, retries=3, backoff_base_s=45.0, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 1
    assert reloj.total == 0.0


def test_un_terminal_a_mitad_corta_la_cadena(peticion, reloj):
    inner = ContadorLlm([LlmRetryableError("429"), LlmTerminalError("400")])

    with pytest.raises(LlmTerminalError):
        RetryingLlm(inner, retries=5, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 2


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------


def test_retries_es_el_total_de_intentos_no_los_extra(peticion, reloj):
    inner = ContadorLlm([LlmRetryableError("x")] * 5)

    with pytest.raises(LlmRetryableError):
        RetryingLlm(inner, retries=3, sleep=reloj).complete_json(peticion)

    assert inner.llamadas == 3


def test_cero_intentos_no_tiene_sentido():
    with pytest.raises(ValueError, match="minimo 1"):
        RetryingLlm(ContadorLlm(), retries=0)

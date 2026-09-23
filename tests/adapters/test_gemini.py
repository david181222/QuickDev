"""El adaptador de Gemini, con un cliente doble. Sin red.

Lo que se prueba aqui es la traduccion en las dos direcciones: peticion nuestra
-> llamada del SDK, y respuesta o excepcion del SDK -> puerto. La clasificacion
de errores tiene test propio por cada clase, porque es la pieza que hacia que el
codigo viejo se quedara 135 segundos dormido ante una API key invalida.
"""

import json

import pytest
from google.genai import errors as genai_errors

from quickdev.adapters.gemini import GeminiAdapter
from quickdev.config import Settings
from quickdev.domain.models import FeedbackReport
from quickdev.ports.llm import LlmRequest, LlmRetryableError, LlmTerminalError

from .dobles import REPORTE_VALIDO, FakeCandidate, FakeClient, FakeSdkResponse


def adaptador(*respuestas, settings=None) -> GeminiAdapter:
    cfg = settings or Settings(_env_file=None, model="modelo-de-prueba")
    return GeminiAdapter(client=FakeClient(*respuestas), settings=cfg)


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------


def test_devuelve_el_json_parseado(peticion):
    ad = adaptador(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))

    r = ad.complete_json(peticion)

    assert r.data == REPORTE_VALIDO
    assert r.attempts == 1
    assert r.truncated is False
    assert r.from_cache is False
    assert r.model == "modelo-de-prueba"
    assert r.latency_s >= 0


def test_agrega_los_tokens_a_usage(peticion):
    ad = adaptador(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))

    r = ad.complete_json(peticion)

    assert r.usage["total_token_count"] == 150
    assert r.usage["prompt_token_count"] == 100


def test_quita_la_valla_de_markdown(peticion):
    """El modelo a veces envuelve el JSON en una valla aunque se le pida JSON."""
    envuelto = "```json\n" + json.dumps(REPORTE_VALIDO) + "\n```"
    ad = adaptador(FakeSdkResponse(text=envuelto))

    assert ad.complete_json(peticion).data == REPORTE_VALIDO


def _config_enviada(response_schema=FeedbackReport):
    cliente = FakeClient(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))
    ad = GeminiAdapter(client=cliente, settings=Settings(_env_file=None))
    peticion = LlmRequest(
        system_prompt="sp",
        payload={"input": "x"},
        response_schema=response_schema,
        temperature=0.0,
        max_output_tokens=4096,
    )
    ad.complete_json(peticion)
    return cliente.models.llamadas[0]["config"]


def test_pasa_el_response_schema_al_proveedor():
    """La forma la hace cumplir el proveedor, no una frase del prompt. ADR-0009."""
    config = _config_enviada()

    dominio = FeedbackReport.model_json_schema()
    assert config.response_schema["properties"] == dominio["properties"]
    assert config.response_schema["required"] == dominio["required"]
    assert config.response_mime_type == "application/json"
    assert config.system_instruction == "sp"
    assert config.temperature == 0.0
    assert config.max_output_tokens == 4096


def test_el_esquema_enviado_no_lleva_additional_properties():
    """`response_schema` de Gemini no acepta `additionalProperties`. ADR-0014.

    Con el modelo Pydantic tal cual, la API respondia 400 en el 100% de las
    llamadas. Este test exigia antes `response_schema is FeedbackReport`: fijaba
    justo el bug, y el cliente doble no valida el esquema, asi que nada lo vio
    hasta la primera corrida real. Lo demas del esquema viaja intacto.
    """
    enviado = _config_enviada().response_schema
    dominio = FeedbackReport.model_json_schema()

    assert "additionalProperties" not in json.dumps(enviado)
    assert enviado["$defs"] == {
        nombre: {k: v for k, v in definicion.items() if k != "additionalProperties"}
        for nombre, definicion in dominio["$defs"].items()
    }


def test_el_dominio_sigue_prohibiendo_campos_extra():
    """Quitarlo del envio no quita la garantia: la frontera de parseo la conserva."""
    assert '"additionalProperties": false' in json.dumps(FeedbackReport.model_json_schema())


def test_sin_esquema_no_se_envia_esquema():
    assert _config_enviada(response_schema=None).response_schema is None


def test_el_payload_viaja_como_json(peticion):
    cliente = FakeClient(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))
    GeminiAdapter(client=cliente, settings=Settings(_env_file=None)).complete_json(peticion)

    assert json.loads(cliente.models.llamadas[0]["contents"]) == peticion.payload


def test_detecta_el_truncamiento(peticion):
    ad = adaptador(
        FakeSdkResponse(
            text=json.dumps(REPORTE_VALIDO),
            candidates=[FakeCandidate(finish_reason="MAX_TOKENS")],
        )
    )

    assert ad.complete_json(peticion).truncated is True


# ---------------------------------------------------------------------------
# Construccion
# ---------------------------------------------------------------------------


def test_sin_api_key_falla_al_construir_no_a_mitad_de_corrida():
    """Falla temprano: una corrida de evals no debe morir con 20 llamadas gastadas."""
    with pytest.raises(LlmTerminalError, match="GEMINI_API_KEY"):
        GeminiAdapter(settings=Settings(_env_file=None, gemini_api_key=""))


def test_no_hay_estado_global_entre_instancias():
    """Lo contrario del `global _client` de motor.py:213-224."""
    a = adaptador(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))
    b = adaptador(FakeSdkResponse(text=json.dumps(REPORTE_VALIDO)))

    assert a.client is not b.client


# ---------------------------------------------------------------------------
# Clasificacion de errores: el corazon del ADR-0006
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("excepcion", "esperado"),
    [
        (genai_errors.ClientError(429, {"error": {"message": "quota"}}), LlmRetryableError),
        (genai_errors.ClientError(408, {"error": {"message": "timeout"}}), LlmRetryableError),
        (genai_errors.ServerError(500, {"error": {"message": "boom"}}), LlmRetryableError),
        (genai_errors.ServerError(503, {"error": {"message": "busy"}}), LlmRetryableError),
        (TimeoutError("se agoto el tiempo"), LlmRetryableError),
        (ConnectionError("sin red"), LlmRetryableError),
        (genai_errors.ClientError(400, {"error": {"message": "bad"}}), LlmTerminalError),
        (genai_errors.ClientError(401, {"error": {"message": "api key"}}), LlmTerminalError),
        (genai_errors.ClientError(403, {"error": {"message": "prohibido"}}), LlmTerminalError),
        (genai_errors.ClientError(404, {"error": {"message": "no existe"}}), LlmTerminalError),
        (ValueError("algo raro del SDK"), LlmTerminalError),
    ],
)
def test_clasificacion_de_errores(peticion, excepcion, esperado):
    ad = adaptador(excepcion)

    with pytest.raises(esperado):
        ad.complete_json(peticion)


def test_un_error_desconocido_es_terminal_no_reintentable(peticion):
    """Al reves que motor.py:383-389, que dormia 135 segundos ante cualquier cosa.

    Un error que no reconocemos es mas probable que sea un bug nuestro que un
    fallo transitorio, y esconderlo detras de tres esperas retrasa el
    diagnostico sin arreglar nada.
    """
    ad = adaptador(RuntimeError("esto no lo habiamos visto"))

    with pytest.raises(LlmTerminalError):
        ad.complete_json(peticion)


# ---------------------------------------------------------------------------
# Respuestas mal formadas
# ---------------------------------------------------------------------------


def test_json_roto_sin_truncamiento_es_reintentable(peticion):
    ad = adaptador(FakeSdkResponse(text="{esto no es json"))

    with pytest.raises(LlmRetryableError):
        ad.complete_json(peticion)


def test_json_roto_por_truncamiento_es_terminal(peticion):
    """Reintentar con temperature=0 da el mismo corte: hay que subir max_output_tokens."""
    ad = adaptador(
        FakeSdkResponse(
            text='{"resumen_general": "se corto a mit',
            candidates=[FakeCandidate(finish_reason="MAX_TOKENS")],
        )
    )

    with pytest.raises(LlmTerminalError, match="max_output_tokens"):
        ad.complete_json(peticion)


def test_un_array_en_la_raiz_es_terminal(peticion):
    """El contrato es un objeto. Una lista no es un reporte."""
    ad = adaptador(FakeSdkResponse(text="[1, 2, 3]"))

    with pytest.raises(LlmTerminalError, match="objeto JSON"):
        ad.complete_json(peticion)

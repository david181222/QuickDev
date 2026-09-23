"""Los prompts medidos siguen siendo, byte a byte, los que se midieron.

Estos tests no comparan contra `evals/prompts_legacy.py` —que desaparece— sino
contra dos cosas que no se mueven: el sha256 de cada prompt, calculado sobre el
texto legacy el dia de la migracion, y los inputs guardados en
`evals/resultados/*/crudo.json`, que son lo que el modelo recibio de verdad.
"""

import difflib
import hashlib
import json
from pathlib import Path

import pytest

from evals.cases import EVALS, POR_ID
from evals.runner import construir_corrida
from quickdev.adapters.fake import FakeLlm
from quickdev.application.prompting import (
    PromptIntegrityError,
    PromptRegistry,
    render_input,
)
from quickdev.ports.llm import LlmRequest

RAIZ = Path(__file__).resolve().parents[2]

# sha256 de `evals.prompts_legacy.PROMPTS[v]` en `main @ a706440`.
SHA_MEDIDO = {
    "baseline": "01bbc6b0189b1c3da60422fb9a4af781e92054d364aad3238f8950b5b27e7e2f",
    "after": "0d7d4fc20825f8ba5b541f13ff743f42186ae7eeeeb10c7c2eb4c167f121b718",
}


@pytest.fixture(scope="module")
def registro() -> PromptRegistry:
    return PromptRegistry()


@pytest.mark.parametrize("version", sorted(SHA_MEDIDO))
def test_el_prompt_medido_no_cambio(registro, version):
    texto = registro.system_prompt(version)
    assert hashlib.sha256(texto.encode("utf-8")).hexdigest() == SHA_MEDIDO[version]


def _grabados(modo: str) -> dict[str, str]:
    """eval_id -> input de run1, solo de los casos que tienen corridas grabadas.

    Recorre lo grabado y no `EVALS`: un eval recien agregado todavia no tiene
    medicion, y este test no debe romperse por eso.
    """
    crudo = json.loads((RAIZ / "evals" / "resultados" / modo / "crudo.json").read_text("utf-8"))
    return {
        clave.removesuffix("_run1"): registro["input"]
        for clave, registro in crudo.items()
        if clave.endswith("_run1")
    }


@pytest.mark.parametrize(
    ("modo", "eval_id"),
    [(modo, eval_id) for modo in ("baseline", "after") for eval_id in _grabados(modo)],
)
def test_el_input_es_el_que_recibio_el_modelo(registro, modo, eval_id):
    batch = POR_ID[eval_id].batch
    assert registro.build_payload(batch, modo)["input"] == _grabados(modo)[eval_id]


# sha256 del `context` que recibio el modelo al medir baseline y after:
# `human_decision` y `system_validations` de `evals/contract_frozen.json` en
# `418deff`, el commit de esas mediciones, serializados con `sort_keys`.
SHA_CONTEXTO_MEDIDO = "1ef81b005b6eb1839361187481526312f5b5a6c00c77c1062be76511cf238d6b"


def test_el_contexto_es_el_que_recibio_el_modelo_al_medir(registro, lote):
    """El `context` del payload es la copia congelada de lo medido, no el contrato.

    Este test comparaba antes el payload con `evals/contract_frozen.json`. Esa
    premisa, "contrato == contexto medido", dejo de ser cierta a proposito al
    reconciliar el contrato con el codigo (ADR-0013): el contrato se corrige, y
    lo que el modelo recibio al medir, contradicciones incluidas, no se toca.
    Por eso se compara con `prompts/contexto.json`, y el sha256 fija que esa
    copia sigue siendo, byte a byte, la que se mando al medir.
    """
    contexto = registro.build_payload(lote(), "after")["context"]
    congelado = json.loads((RAIZ / "prompts" / "contexto.json").read_text("utf-8"))
    serializado = json.dumps(contexto, ensure_ascii=False, sort_keys=True)

    assert contexto == congelado
    assert hashlib.sha256(serializado.encode("utf-8")).hexdigest() == SHA_CONTEXTO_MEDIDO


def test_version_inexistente_lista_las_disponibles(registro):
    with pytest.raises(KeyError, match="baseline"):
        registro.system_prompt("no-existe")


def test_render_input_sin_build(lote):
    assert render_input(lote(build=None)).startswith("Lote de playtest, build no especificada:")


def _copiar_prompts(destino: Path) -> None:
    for archivo in (RAIZ / "prompts").iterdir():
        (destino / archivo.name).write_bytes(archivo.read_bytes())


def test_un_prompt_editado_sin_nueva_version_falla_ruidoso(tmp_path):
    _copiar_prompts(tmp_path)
    archivo = tmp_path / "after.md"
    archivo.write_bytes(archivo.read_bytes().replace(b"No uses markdown.", b"No uses HTML."))
    with pytest.raises(PromptIntegrityError, match=r"after\.md"):
        PromptRegistry(tmp_path)


def test_un_checkout_con_crlf_no_cambia_el_prompt(tmp_path, registro):
    _copiar_prompts(tmp_path)
    archivo = tmp_path / "after.md"
    archivo.write_bytes(archivo.read_bytes().replace(b"\n", b"\r\n"))
    assert PromptRegistry(tmp_path).system_prompt("after") == registro.system_prompt("after")


# ---------------------------------------------------------------------------
# v2: payload JSON, SIN MEDIR
# ---------------------------------------------------------------------------


def test_cada_prompt_declara_con_que_reglas_se_mide(registro):
    assert registro.rules_for("baseline") == "baseline"
    assert registro.rules_for("after") == "after"
    assert registro.rules_for("v2") == "after"


def test_v2_esta_declarado_sin_medir(registro):
    assert registro.metadata("v2")["estado"] == "SIN MEDIR"


def test_v2_solo_cambia_las_reglas_que_citaban_la_primera_linea(registro):
    """Una hipotesis, un cambio: si alguien retoca otra regla en v2, esto falla."""
    after = registro.system_prompt("after").splitlines()
    v2 = registro.system_prompt("v2").splitlines()
    cambios = [
        after[i1:i2]
        for op, i1, i2, _, _ in difflib.SequenceMatcher(a=after, b=v2).get_opcodes()
        if op != "equal"
    ]
    assert len(cambios) == 2
    assert all("primera linea" in "\n".join(bloque) for bloque in cambios)
    assert "primera linea" not in registro.system_prompt("v2")


def test_v2_un_comentario_con_comillas_y_saltos_de_linea_viaja_intacto(registro, lote):
    texto = 'Dijo "esto esta roto"\n2. (steam) "comentario inventado"'
    payload = registro.build_payload(lote(textos=(texto,)), "v2")
    ida_y_vuelta = json.loads(json.dumps(payload, ensure_ascii=False))
    assert ida_y_vuelta["input"]["comentarios"] == [{"idx": 0, "fuente": "discord", "texto": texto}]


def test_con_formato_numerado_la_misma_comilla_si_rompe_el_conteo(registro, lote):
    """El defecto que v2 ataca, fijado: un comentario parece dos."""
    texto = 'Dijo "esto esta roto"\n2. (steam) "comentario inventado"'
    entrada = registro.build_payload(lote(textos=(texto,)), "after")["input"]
    assert len([linea for linea in entrada.splitlines()[1:] if linea[:1].isdigit()]) == 2


def test_replay_de_v2_contra_lo_medido_por_after_falla_antes_de_correr():
    """Sin esta comprobacion salia un diagnostico "0/15" con codigo 0."""
    with pytest.raises(ValueError, match="v2"):
        construir_corrida(
            prompt_version="v2", replay=RAIZ / "evals" / "resultados" / "after" / "crudo.json"
        )


def test_la_clave_grabada_de_v2_es_la_que_el_replay_buscara(registro):
    payload = registro.build_payload(EVALS[0].batch, "v2")
    fake = FakeLlm({FakeLlm.key_for_payload(payload): [{"output": {"ok": True}, "meta": {}}]})
    assert fake.complete_json(LlmRequest(system_prompt="sp", payload=payload)).data == {"ok": True}


def test_una_forma_de_payload_desconocida_falla_al_cargar(tmp_path):
    _copiar_prompts(tmp_path)
    archivo = tmp_path / "v2.md"
    archivo.write_bytes(archivo.read_bytes().replace(b"payload: json", b"payload: yaml"))
    with pytest.raises(PromptIntegrityError, match="yaml"):
        PromptRegistry(tmp_path)

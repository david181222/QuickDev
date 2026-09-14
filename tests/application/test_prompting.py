"""Los prompts medidos siguen siendo, byte a byte, los que se midieron.

Estos tests no comparan contra `evals/prompts_legacy.py` —que desaparece— sino
contra dos cosas que no se mueven: el sha256 de cada prompt, calculado sobre el
texto legacy el dia de la migracion, y los inputs guardados en
`evals/resultados/*/crudo.json`, que son lo que el modelo recibio de verdad.
"""

import hashlib
import json
from pathlib import Path

import pytest

from evals.cases import EVALS
from quickdev.application.prompting import (
    PromptIntegrityError,
    PromptRegistry,
    render_input,
)

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


@pytest.mark.parametrize("modo", ["baseline", "after"])
@pytest.mark.parametrize("case", EVALS, ids=lambda c: c.id)
def test_el_input_es_el_que_recibio_el_modelo(registro, modo, case):
    crudo = json.loads((RAIZ / "evals" / "resultados" / modo / "crudo.json").read_text("utf-8"))
    grabado = crudo[f"{case.id}_run1"]["input"]
    assert registro.build_payload(case.batch)["input"] == grabado


def test_el_contexto_es_el_del_contrato_con_el_que_se_midio(registro, lote):
    contrato = json.loads((RAIZ / "evals" / "contract_frozen.json").read_text("utf-8"))
    assert registro.build_payload(lote())["context"] == {
        "human_decision": contrato["human_decision"],
        "system_validations": contrato["system_validations"],
    }


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

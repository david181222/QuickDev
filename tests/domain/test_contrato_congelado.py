"""El contrato escrito dice lo mismo que el codigo en los valores cerrados.

`evals/contract_frozen.json` lo genero un modelo al principio del proyecto y no
se reconcilio con el codigo hasta el ADR-0013: declaraba como fuentes 'Discord',
'Google Forms' y 'Mensaje Directo', cuando el enum que se valida es otro. Estos
tests impiden que vuelvan a divergir en silencio.

El criterio: en las secciones normativas del contrato, toda lista cerrada se
escribe `a | b | c`, y cada una tiene que ser EXACTAMENTE uno de los vocabularios
de `quickdev/domain/models.py`, ni un valor de mas ni uno de menos. Las secciones
narrativas (`jtbd`, `current_alternative`...) cuentan donde vive hoy el feedback
de un playtest, no que acepta el sistema, y no se comprueban.
"""

import json
import re
from pathlib import Path
from typing import get_args

import pytest

from quickdev.domain.models import Categoria, Fuente, MotivoDescarte, Prioridad, Sentimiento

CONTRATO = Path(__file__).resolve().parents[2] / "evals" / "contract_frozen.json"

VOCABULARIOS = {
    "Fuente": frozenset(get_args(Fuente)),
    "Categoria": frozenset(get_args(Categoria)),
    "Prioridad": frozenset(get_args(Prioridad)),
    "Sentimiento": frozenset(get_args(Sentimiento)),
    "MotivoDescarte": frozenset(get_args(MotivoDescarte)),
}

SECCIONES_NORMATIVAS = ("input_required", "ai_job", "system_validations", "output_fields")

LISTA_CERRADA = re.compile(r"[a-z_]+(?: \| [a-z_]+)+")


def _textos(valor) -> list[str]:
    """Todos los strings de una seccion, sea string, lista o diccionario."""
    if isinstance(valor, str):
        return [valor]
    if isinstance(valor, list):
        return [t for v in valor for t in _textos(v)]
    if isinstance(valor, dict):
        return [t for v in valor.values() for t in _textos(v)]
    return []


@pytest.fixture(scope="module")
def normativo() -> str:
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))
    return "\n".join(t for seccion in SECCIONES_NORMATIVAS for t in _textos(contrato[seccion]))


def listas_cerradas(texto: str) -> list[frozenset[str]]:
    """Cada `a | b | c` del texto, sin `null`: admitir null no es un valor del vocabulario."""
    return [
        frozenset(v.strip() for v in lista.split("|")) - {"null"}
        for lista in LISTA_CERRADA.findall(texto)
    ]


def test_toda_lista_cerrada_del_contrato_es_un_vocabulario_del_codigo(normativo):
    for lista in listas_cerradas(normativo):
        assert lista in VOCABULARIOS.values(), (
            f"el contrato declara {sorted(lista)}, que no coincide con ningun vocabulario "
            f"de quickdev/domain/models.py"
        )


@pytest.mark.parametrize("nombre", sorted(VOCABULARIOS))
def test_el_contrato_declara_cada_vocabulario_completo(normativo, nombre):
    assert VOCABULARIOS[nombre] in listas_cerradas(normativo), (
        f"el contrato no declara '{nombre}' como lista cerrada: "
        f"{' | '.join(sorted(VOCABULARIOS[nombre]))}"
    )


@pytest.mark.parametrize("ajena", ["Google Forms", "Mensaje Directo"])
def test_ninguna_fuente_ajena_al_enum(normativo, ajena):
    """Las dos fuentes que el contrato original inventaba y el codigo nunca acepto."""
    assert ajena.lower() not in normativo.lower()

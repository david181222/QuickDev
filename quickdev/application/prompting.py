"""De donde salen los prompts.

Responsabilidad: servir, por version, el prompt de sistema y el payload con el
que se llama al modelo. Los textos viven en `prompts/*.md`, no en el codigo,
para que sean versionables y diffeables: un cambio de prompt es un cambio de
comportamiento, y tiene que poder revisarse como tal.

Lo que NO le corresponde: llamar al modelo, validar la respuesta ni decidir que
version se usa (eso lo dice `Settings.prompt_version`).

## Un prompt medido es un archivo congelado

Cada `prompts/<version>.md` guarda el prompt de sistema YA RENDERIZADO, no una
plantilla. El prompt original interpolaba `evals/contract_frozen.json`, y ese
archivo tiene contradicciones pendientes de reconciliar: si el prompt fuera una
plantilla, reconciliar el contrato cambiaria en silencio el texto con el que se
midieron `baseline/` y `after/`. Por lo mismo, el `context` del payload sale de
`prompts/contexto.json`, una copia congelada, y no del contrato.

El front matter declara el `sha256` del texto, y el registro lo comprueba al
cargar. Un editor que quite un salto de linea, o un checkout de Windows que meta
`\\r\\n`, no puede cambiar el prompt sin que se note: el primero falla ruidoso, el
segundo se normaliza antes de comprobar.
"""

import hashlib
import json
from pathlib import Path
from typing import Protocol

from quickdev.domain.models import PlaytestBatch

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


class PromptProvider(Protocol):
    """Provee el prompt de sistema y el payload de una version dada."""

    def system_prompt(self, version: str) -> str:
        """El texto del prompt de sistema de esa version.

        Raises:
            KeyError: si la version no existe, listando las disponibles.
        """
        ...

    def build_payload(self, batch: PlaytestBatch) -> dict:
        """Arma el payload de datos que acompana al prompt.

        Hoy los comentarios viajan como un string numerado (`render_input`),
        que es la forma con la que se midieron `baseline/` y `after/`. Esa
        forma se rompe si un comentario contiene comillas o saltos de linea;
        cambiarla cambia lo que recibe el modelo, asi que se hace en una version
        de prompt nueva y se mide, no se desliza aqui.
        """
        ...


class PromptIntegrityError(ValueError):
    """El texto de un prompt no coincide con el sha256 que declara su archivo."""


def render_input(batch: PlaytestBatch) -> str:
    """El texto del input, byte por byte como lo producia `motor.py:build_input`.

    La primera linea declara la build analizada, y eso no es cosmetico: es lo que
    permite al prompt `after` desempatar entre la build del lote y una version
    citada dentro de un comentario.
    """
    encabezado = (
        f"Lote de playtest, build {batch.build}:"
        if batch.build
        else "Lote de playtest, build no especificada:"
    )
    cuerpo = "\n".join(
        f'{i}. ({c.fuente}) "{c.texto}"' for i, c in enumerate(batch.comentarios, start=1)
    )
    return encabezado + "\n" + cuerpo


def _leer_prompt(archivo: Path) -> tuple[dict[str, str], str]:
    """Separa el front matter del texto del prompt. El texto se devuelve intacto."""
    texto = archivo.read_bytes().decode("utf-8").replace("\r\n", "\n")
    if not texto.startswith("---\n"):
        raise PromptIntegrityError(f"{archivo.name}: falta el front matter inicial '---'.")
    fin = texto.find("\n---", 4)
    if fin == -1:
        raise PromptIntegrityError(f"{archivo.name}: el front matter no se cierra con '---'.")

    meta: dict[str, str] = {}
    for linea in texto[4:fin].splitlines():
        clave, sep, valor = linea.partition(":")
        if sep:
            meta[clave.strip()] = valor.strip()
    return meta, texto[fin + len("\n---") :]


class PromptRegistry:
    """Implementa `PromptProvider` leyendo `prompts/*.md`."""

    def __init__(self, directorio: Path = PROMPTS_DIR) -> None:
        self.directorio = Path(directorio)
        self._prompts: dict[str, str] = {}
        self._meta: dict[str, dict[str, str]] = {}

        for archivo in sorted(self.directorio.glob("*.md")):
            if archivo.name.lower() == "readme.md":
                continue
            meta, cuerpo = _leer_prompt(archivo)
            version = meta.get("version", archivo.stem)
            esperado = meta.get("sha256")
            real = hashlib.sha256(cuerpo.encode("utf-8")).hexdigest()
            if esperado != real:
                raise PromptIntegrityError(
                    f"{archivo.name}: el texto no coincide con su sha256 declarado "
                    f"(declarado {esperado}, real {real}). Si el cambio es intencionado, "
                    f"es una version de prompt nueva: se crea otro archivo y se mide."
                )
            self._prompts[version] = cuerpo
            self._meta[version] = meta

        self._contexto = json.loads((self.directorio / "contexto.json").read_text(encoding="utf-8"))

    @property
    def versions(self) -> tuple[str, ...]:
        return tuple(self._prompts)

    def metadata(self, version: str) -> dict[str, str]:
        """El front matter de esa version: estado, medicion, descripcion..."""
        self._comprobar(version)
        return dict(self._meta[version])

    def system_prompt(self, version: str) -> str:
        """
        Raises:
            KeyError: la version no existe, listando las disponibles.
        """
        self._comprobar(version)
        return self._prompts[version]

    def build_payload(self, batch: PlaytestBatch) -> dict:
        """El payload con la forma con la que se midieron baseline y after."""
        return {
            "input": render_input(batch),
            "context": dict(self._contexto),
        }

    def _comprobar(self, version: str) -> None:
        if version not in self._prompts:
            raise KeyError(f"No existe el prompt '{version}'. Disponibles: {sorted(self._prompts)}")

"""La regla estructural del proyecto, ejecutable.

`docs/arquitectura.md` (seccion 3) afirma que las flechas apuntan siempre hacia
adentro: nada de `quickdev/domain/` sabe que existen los adaptadores. La seccion
7 dice que eso "es verificable, no un acuerdo verbal" y ofrece un grep. Este
archivo es ese grep convertido en test, por la misma razon que el resto del
proyecto existe: una instruccion en un documento no es una garantia; una
comprobacion que corre en cada `pytest` si.

## Por que AST y no el grep

El grep de la documentacion busca cinco nombres escritos a mano:

    ^\\s*(import|from)\\s+(google|pandas|requests|os|pathlib)

Atrapa lo que ya sabiamos que habia que prohibir, y deja pasar todo lo demas:
`import httpx`, `import socket` y, sobre todo, `from quickdev.adapters import
GeminiAdapter`, que es precisamente la violacion que invertiria la direccion de
las dependencias y la unica que la arquitectura no podria sobrevivir. Leer los
imports del AST no necesita saber de antemano que nombres prohibir: invierte la
pregunta y exige que cada import este justificado.

Ademas no da los falsos positivos que el propio documento avisa: los docstrings
del paquete mencionan "genai" y "pandas" al explicar justamente esta regla, y un
grep de texto los cuenta como violaciones.

## Que se permite y por que

- `quickdev.domain.*`: hacia adentro, o lateral dentro del nucleo.
- `pydantic`: la unica dependencia externa del dominio. Es una libreria de
  modelado de datos, no de infraestructura: no abre sockets, no lee disco y no
  sabe que existe un proveedor de modelos. Que `models.py` la use es la decision
  del ADR-0002 (interoperar con `BaseModel` y `model_validate`).
- La stdlib, EXCEPTO los modulos que salen del proceso (disco, red, subprocesos,
  entorno). El dominio se describe a si mismo como "sin modelo, sin red, sin
  I/O", y `os` y `pathlib` ya estaban en la lista del grep original.

Cualquier otra cosa falla. Ver ADR-0001.
"""

import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
DOMINIO = RAIZ / "quickdev" / "domain"

# Los modulos del nucleo, escritos a mano a proposito: si alguien anade un
# archivo a `domain/` y no lo apunta aqui, `test_el_barrido_cubre_el_dominio`
# se pone en rojo. Un barrido que se queda corto en silencio es peor que no
# tenerlo: da un OK sobre codigo que nadie miro.
MODULOS_ESPERADOS = frozenset(
    {
        "__init__.py",
        "models.py",
        "validation.py",
        "rules/__init__.py",
        "rules/base.py",
        "rules/citations.py",
        "rules/counts.py",
        "rules/registry.py",
        "rules/review.py",
        "rules/versioning.py",
    }
)

# La unica dependencia externa que el dominio puede importar.
TERCEROS_PERMITIDOS = frozenset({"pydantic"})

# Stdlib que si sale del proceso. No es una lista de todo lo prohibido (eso lo
# cubre el allowlist de arriba), sino de lo que es stdlib Y ademas es I/O, que
# de otro modo pasaria por ser "de la libreria estandar".
STDLIB_CON_EFECTOS = frozenset(
    {
        "asyncio",
        "ftplib",
        "http",
        "io",
        "multiprocessing",
        "os",
        "pathlib",
        "pickle",
        "shutil",
        "signal",
        "socket",
        "sqlite3",
        "subprocess",
        "tempfile",
        "threading",
        "urllib",
        "webbrowser",
    }
)


def _modulos_del_dominio() -> list[Path]:
    return sorted(DOMINIO.rglob("*.py"))


def _relativo(archivo: Path) -> str:
    return archivo.relative_to(DOMINIO).as_posix()


def _paquete_de(archivo: Path) -> str:
    """El paquete que contiene ese archivo.

    `quickdev/domain/rules/base.py` -> `quickdev.domain.rules`.
    """
    return ".".join(archivo.relative_to(RAIZ).with_suffix("").parts[:-1])


def _imports(archivo: Path):
    """Cada import del archivo, como `(modulo_absoluto, linea)`.

    Los imports relativos se resuelven contra el paquete del archivo, porque
    `from .models import X` y `from quickdev.domain.models import X` son la misma
    dependencia y tienen que juzgarse igual.
    """
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                yield alias.name, nodo.lineno
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.level:
                partes = _paquete_de(archivo).split(".")
                base = ".".join(partes[: len(partes) - (nodo.level - 1)])
                yield (f"{base}.{nodo.module}" if nodo.module else base), nodo.lineno
            else:
                yield (nodo.module or ""), nodo.lineno


def _veredicto(modulo: str) -> str | None:
    """El motivo por el que ese import no deberia estar, o None si es legitimo."""
    raiz = modulo.split(".")[0]

    if modulo == "quickdev.domain" or modulo.startswith("quickdev.domain."):
        return None
    if raiz == "quickdev":
        return (
            "importa otra capa de quickdev. La direccion de las dependencias es "
            "hacia adentro: si el dominio necesita esto, el dato tiene que "
            "entrar por parametro (ver ADR-0001)"
        )
    if raiz in TERCEROS_PERMITIDOS:
        return None
    if raiz in STDLIB_CON_EFECTOS:
        return "es I/O: el dominio no toca disco, red, procesos ni entorno"
    if raiz in sys.stdlib_module_names:
        return None
    return "es una dependencia externa; la unica permitida en el dominio es pydantic"


@pytest.mark.parametrize("archivo", _modulos_del_dominio(), ids=_relativo)
def test_el_dominio_solo_importa_hacia_adentro(archivo):
    """Ningun modulo del nucleo importa infraestructura, otra capa, ni I/O."""
    violaciones = [
        f"{_relativo(archivo)}:{linea}  import {modulo}  ->  {motivo}"
        for modulo, linea in _imports(archivo)
        if (motivo := _veredicto(modulo))
    ]
    assert not violaciones, "\n".join(
        [
            "el dominio dejo de ser puro y con eso se cae la tesis del proyecto:",
            *violaciones,
        ]
    )


def test_el_barrido_cubre_el_dominio():
    """El test de arriba no vale nada si no esta mirando los archivos que cree.

    Un barrido vacio (por un rename, un `rglob` que no casa o una carpeta movida)
    daria PASS sobre cero archivos. Que la lista sea explicita convierte eso en un
    fallo ruidoso, y obliga a que anadir un modulo al dominio sea deliberado.
    """
    encontrados = {_relativo(a) for a in _modulos_del_dominio()}
    assert encontrados == MODULOS_ESPERADOS, (
        "los modulos de quickdev/domain/ cambiaron. Si es deliberado, actualiza "
        "MODULOS_ESPERADOS; si no, algo se movio de sitio.\n"
        f"  sin revisar: {sorted(encontrados - MODULOS_ESPERADOS)}\n"
        f"  desaparecidos: {sorted(MODULOS_ESPERADOS - encontrados)}"
    )


def test_el_veredicto_reconoce_las_violaciones_que_el_grep_no_veia():
    """El caso que justifica este archivo.

    Los tres primeros son los que un grep de `google|pandas|requests|os|pathlib`
    dejaba pasar, y el ultimo es el unico que ese grep atrapaba. No se comprueba
    que el dominio los tenga (no los tiene): se comprueba que el veredicto los
    reconoceria, para que este test no pueda quedarse callado por un bug propio.
    """
    assert _veredicto("quickdev.adapters.gemini")
    assert _veredicto("quickdev.ports.llm")
    assert _veredicto("httpx")
    assert _veredicto("pathlib")

    assert _veredicto("quickdev.domain.models") is None
    assert _veredicto("pydantic") is None
    assert _veredicto("dataclasses") is None

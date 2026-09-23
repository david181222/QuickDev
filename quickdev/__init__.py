"""QuickDev: analisis de feedback de playtesters de videojuegos.

La tesis del producto, que ordena todo el paquete:

    El modelo interpreta lenguaje. El codigo verifica hechos.

El modelo clasifica, agrupa por tema, resume y detecta tono. Codigo determinista
comprueba los conteos contra `len()`, los enums contra listas cerradas, y que
cada cita exista literalmente en el lote. Una instruccion en el prompt no es una
garantia; una validacion posterior si.

Arquitectura (puertos y adaptadores). La dependencia apunta siempre hacia
adentro: nada de `domain/` sabe que existe `adapters/`.

    domain/         el contrato, los modelos y las reglas. PURO: sin I/O,
                    sin SDK, sin pandas.
    ports/          las interfaces que el dominio necesita del exterior.
    adapters/       las implementaciones concretas. El unico lugar del repo
                    que importa `google.genai`.
    application/    el caso de uso: ordena los pasos del flujo.
    observability/  la traza de cada ejecucion.

Ver `docs/adr/0001-arquitectura-hexagonal.md` para por que, y
`PROMPTS_EQUIPO.md` para quien esta implementando cada parte.
"""

__version__ = "0.1.0"

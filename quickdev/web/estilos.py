"""Estilos y piezas de presentacion de la interfaz web.

Responsabilidad: que la app se vea bien. Los colores base y las fuentes viven en
`.streamlit/config.toml`; aqui solo hay el CSS que el tema no cubre y los
traductores de valores del contrato a etiquetas legibles.

Todo el CSS usa colores con transparencia o `inherit`, para que funcione igual
en el tema claro y en el oscuro sin duplicar reglas.
"""

import re

CSS = """
<style>
.block-container { max-width: 1180px; padding-top: 2.2rem; padding-bottom: 4rem; }

.qd-hero {
    padding: 1.6rem 1.8rem;
    border-radius: 1rem;
    border: 1px solid rgba(124, 110, 240, 0.25);
    background: linear-gradient(135deg, rgba(124, 110, 240, 0.14), rgba(56, 189, 248, 0.08));
    margin-bottom: 0.4rem;
}
.qd-hero .qd-marca {
    font-size: 2.1rem;
    font-weight: 700;
    letter-spacing: -0.02em;
    line-height: 1.15;
    margin: 0;
}
.qd-hero .qd-sub {
    font-size: 1.05rem;
    opacity: 0.82;
    margin: 0.45rem 0 0.9rem 0;
    line-height: 1.55;
}
.qd-hero .qd-tesis {
    display: inline-block;
    font-size: 0.92rem;
    font-weight: 600;
    padding: 0.3rem 0.8rem;
    border-radius: 0.8rem;
    background: rgba(124, 110, 240, 0.16);
}

.qd-paso {
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    opacity: 0.6;
    margin: 0.6rem 0 -0.6rem 0;
}

.qd-cita {
    border-left: 3px solid rgba(124, 110, 240, 0.7);
    padding: 0.2rem 0 0.2rem 0.9rem;
    margin: 0.2rem 0 0.2rem 0;
    font-size: 1rem;
    line-height: 1.55;
}

[data-testid="stMetricValue"] { font-weight: 650; }
[data-testid="stMetricLabel"] p { font-weight: 500; opacity: 0.75; }
button[data-baseweb="tab"] p { font-size: 0.98rem; font-weight: 500; }
</style>
"""


def encabezado() -> str:
    """La cabecera de la pagina: marca, para que sirve y la tesis del producto."""
    return """
<div class="qd-hero">
  <p class="qd-marca">🎮 QuickDev</p>
  <p class="qd-sub">
    Analiza el feedback de un playtest cerrado y entrega un reporte: resumen, sentimiento,
    problemas priorizados, citas de evidencia y comentarios descartados con su motivo.
  </p>
  <span class="qd-tesis">El modelo interpreta lenguaje · El código verifica hechos</span>
</div>
"""


def paso(texto: str) -> str:
    """Un rotulo pequeno sobre cada seccion ("Paso 1", "Paso 2")."""
    return f'<p class="qd-paso">{texto}</p>'


# ---------------------------------------------------------------------------
# valores del contrato -> etiquetas
# ---------------------------------------------------------------------------
# Los colores son los de las insignias de Markdown de Streamlit
# (`:red-badge[...]`), que ya se adaptan al tema claro y al oscuro.

_PRIORIDAD = {"alta": ("red", "Alta"), "media": ("orange", "Media"), "baja": ("green", "Baja")}
_SENTIMIENTO = {
    "positivo": ("green", "Positivo"),
    "neutro": ("gray", "Neutro"),
    "negativo": ("red", "Negativo"),
}
_MOTIVO = {
    "ruido": ("gray", "Ruido"),
    "sesgado": ("orange", "Sesgado"),
    "extremista": ("red", "Extremista"),
    "sin_relacion": ("blue", "Sin relación"),
}
_FUENTE = {
    "discord": "💬 Discord",
    "steam": "🎮 Steam",
    "encuesta": "📝 Encuesta",
    "red_social": "📣 Red social",
}
_CATEGORIA = {
    "balance": "Balance",
    "bugs": "Bugs",
    "dificultad": "Dificultad",
    "rendimiento": "Rendimiento",
    "interfaz": "Interfaz",
    "diversion": "Diversión",
    "economia": "Economía",
    "otro": "Otro",
}

ORDEN_PRIORIDAD = {"alta": 0, "media": 1, "baja": 2}


def _insignia(color: str, texto: str) -> str:
    return f":{color}-badge[{texto}]"


def prioridad(valor: str) -> str:
    return _insignia(*_PRIORIDAD.get(valor, ("gray", valor)))


def motivo(valor: str) -> str:
    return _insignia(*_MOTIVO.get(valor, ("gray", valor)))


def categoria(valor: str) -> str:
    return _insignia("violet", _CATEGORIA.get(valor, valor))


def sentimiento(valor: str) -> str:
    """El sentimiento sin insignia, para el valor de una metrica."""
    return _SENTIMIENTO.get(valor, ("gray", valor))[1]


def fuente(valor: str | None) -> str:
    if not valor:
        return "fuente no indicada"
    return _FUENTE.get(valor, valor)


# ---------------------------------------------------------------------------

_ESPECIALES_MD = re.compile(r"([\\`*_{}\[\]<>()#+\-!|~$:])")


def literal(texto: str) -> str:
    """El texto de un jugador, tal cual, sin que Streamlit lo lea como Markdown.

    Un comentario con asteriscos o corchetes se veria alterado (o, peor, como un
    enlace). Las citas tienen que mostrarse literales: es justo lo que el
    validador comprueba.
    """
    return _ESPECIALES_MD.sub(r"\\\1", texto)

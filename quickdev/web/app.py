"""La interfaz web: `streamlit run quickdev/web/app.py` desde la raiz del repo.

Responsabilidad: la misma que la CLI, con otra cara. Arma el lote (un ejemplo
medido, un JSON subido o comentarios escritos a mano), compone el caso de uso con
`construir_analisis` y muestra el `AnalysisResult`.

Lo que NO le corresponde: ninguna logica del producto. Si una funcion de aqui
empieza a decidir algo sobre el reporte, esta en el sitio equivocado; ver el
docstring de `quickdev/cli.py`.

## Los dos modos

- Demo: `FakeLlm` sobre las respuestas grabadas en `evals/resultados/`. Sin red
  ni API key, pero solo responde a los lotes que se midieron (los ejemplos). Un
  lote nuevo no tiene respuesta grabada y se avisa en vez de fallar.
- Gemini en vivo: la composicion de produccion (`build_llm`). Usa la
  `GEMINI_API_KEY` del `.env` o una pegada en la barra lateral, que vive solo en
  la sesion del navegador y nunca se escribe a disco.
"""

import html
from pathlib import Path
from typing import get_args

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from evals.cases import EVALS
from quickdev.adapters import FakeLlm, SinRespuestaGrabada, build_llm
from quickdev.application.prompting import PromptRegistry
from quickdev.application.types import AnalysisResult
from quickdev.cli import RAIZ, _como_json, construir_analisis
from quickdev.config import Settings
from quickdev.domain.models import Fuente, PlaytestBatch, PlaytestComment
from quickdev.domain.rules.registry import rule_set
from quickdev.ports.llm import LlmError
from quickdev.web import estilos

# Las respuestas grabadas por version de prompt. `v2` no tiene: esta sin medir.
CRUDOS: dict[str, Path] = {
    "after": RAIZ / "evals" / "resultados" / "after" / "crudo.json",
    "baseline": RAIZ / "evals" / "resultados" / "baseline" / "crudo.json",
}

DEMO = "demo"
VIVO = "vivo"

ORIGEN_EJEMPLO = "📚 Ejemplos medidos"
ORIGEN_JSON = "📂 Subir JSON"
ORIGEN_MANUAL = "✍️ Escribir comentarios"


# ---------------------------------------------------------------------------
# barra lateral
# ---------------------------------------------------------------------------


def barra_lateral(registro: PromptRegistry) -> tuple[str, str, str]:
    """Modo, prompt y clave. Devuelve (modo, prompt_version, api_key)."""
    with st.sidebar:
        st.markdown("### ⚙️ Configuración")

        modo = st.radio(
            "Cómo se consulta al modelo",
            [DEMO, VIVO],
            format_func=lambda m: {
                DEMO: "Demo sin API key",
                VIVO: "Gemini en vivo",
            }[m],
            help=(
                "La demo reproduce respuestas reales ya grabadas: no usa internet, pero solo "
                "funciona con los ejemplos medidos. En vivo llama a Gemini con tu clave y "
                "sirve para cualquier lote."
            ),
        )

        versiones = sorted(registro.versions)
        prompt = st.selectbox(
            "Versión del prompt",
            versiones,
            index=versiones.index("after") if "after" in versiones else 0,
            format_func=lambda v: f"{v} · {registro.metadata(v).get('estado', '')}",
        )
        meta = registro.metadata(prompt)
        st.caption(meta.get("descripcion", ""))
        st.caption(f"Reglas de validación: **{registro.rules_for(prompt)}**")

        api_key = ""
        if modo == DEMO and prompt not in CRUDOS:
            st.warning(
                f"El prompt `{prompt}` no tiene respuestas grabadas. "
                "Usa `after` o `baseline`, o cambia a Gemini en vivo."
            )
        if modo == VIVO:
            api_key = Settings().gemini_api_key
            if api_key:
                st.success("Clave de Gemini encontrada en `.env`.", icon="🔑")
            else:
                api_key = st.text_input(
                    "GEMINI_API_KEY",
                    type="password",
                    help="Solo se usa en esta sesión; no se guarda en ningún archivo.",
                )
                st.caption("Consíguela en [Google AI Studio](https://aistudio.google.com/apikey).")

        st.divider()
        st.markdown(
            "**Cómo leer el resultado**\n\n"
            "- El **modelo** clasifica, agrupa, resume y prioriza.\n"
            "- El **código** comprueba conteos, citas y versión, y corrige lo que puede.\n"
            "- Una **persona** decide qué se arregla en la siguiente build."
        )
    return modo, prompt, api_key


# ---------------------------------------------------------------------------
# paso 1: el lote
# ---------------------------------------------------------------------------


def lote_de_ejemplo() -> PlaytestBatch:
    caso = st.selectbox(
        "Ejemplo",
        EVALS,
        format_func=lambda c: f"{c.categoria} — {c.batch.total} comentarios",
    )
    with st.expander("¿Qué pone a prueba este ejemplo?"):
        st.write(caso.hipotesis)
    return caso.batch


def lote_desde_json() -> PlaytestBatch | None:
    archivo = st.file_uploader(
        "Archivo del lote",
        type=["json"],
        help='Formato: {"build": "v0.8.2", "comentarios": [{"fuente": "discord", "texto": "..."}]}',
    )
    st.caption(
        "Fuentes permitidas: "
        + ", ".join(f"`{f}`" for f in get_args(Fuente))
        + ". Mira `docs/ejemplos/lote_normal.json` como modelo."
    )
    if archivo is None:
        return None
    try:
        return PlaytestBatch.model_validate_json(archivo.getvalue())
    except ValidationError as exc:
        st.error("El archivo no tiene el formato de un lote:\n\n" + _errores_legibles(exc))
        return None


def lote_manual() -> PlaytestBatch | None:
    build = st.text_input("Build analizada", placeholder="v0.9.0 (déjalo vacío si no se sabe)")
    tabla = st.data_editor(
        pd.DataFrame(
            {
                "fuente": ["discord", "steam", "encuesta"],
                "texto": ["", "", ""],
            }
        ),
        key="comentarios_manuales",
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "fuente": st.column_config.SelectboxColumn(
                "Fuente", options=list(get_args(Fuente)), required=True, width="small"
            ),
            "texto": st.column_config.TextColumn("Comentario del jugador", width="large"),
        },
    )
    comentarios = [
        PlaytestComment(fuente=fila.fuente, texto=str(fila.texto).strip())
        for fila in tabla.itertuples()
        if isinstance(fila.texto, str) and fila.texto.strip() and fila.fuente
    ]
    if not comentarios:
        st.info("Escribe al menos un comentario para poder analizar.")
        return None
    return PlaytestBatch(build=build.strip() or None, comentarios=comentarios)


def vista_previa(batch: PlaytestBatch) -> None:
    st.caption(f"**{batch.total} comentarios** · build **{batch.build or 'no especificada'}**")
    st.dataframe(
        pd.DataFrame(
            [{"fuente": estilos.fuente(c.fuente), "texto": c.texto} for c in batch.comentarios]
        ),
        hide_index=True,
        column_config={
            "fuente": st.column_config.TextColumn("Fuente", width="small"),
            "texto": st.column_config.TextColumn("Comentario", width="large"),
        },
        height=min(38 + 35 * batch.total, 300),
    )


# ---------------------------------------------------------------------------
# el analisis
# ---------------------------------------------------------------------------


def analizar(batch: PlaytestBatch, modo: str, prompt: str, api_key: str) -> AnalysisResult:
    """Compone y ejecuta. Las mismas piezas que `quickdev analyze`."""
    rules = PromptRegistry().rules_for(prompt)
    if modo == DEMO:
        # Un FakeLlm nuevo por analisis: consume las corridas en orden, y la
        # primera es la que se mostraria siempre en `quickdev demo`.
        llm = FakeLlm.from_crudo(CRUDOS[prompt])
    else:
        settings = Settings(gemini_api_key=api_key, prompt_version=prompt, rules_version=rules)
        llm = build_llm(settings)
    return construir_analisis(llm, prompt, rules).execute(batch)


def _errores_legibles(exc: ValidationError) -> str:
    lineas = []
    for e in exc.errors()[:6]:
        donde = " → ".join(str(p) for p in e["loc"]) or "raíz"
        lineas.append(f"- `{donde}`: {e['msg']}")
    return "\n".join(lineas)


def ejecutar(batch: PlaytestBatch, modo: str, prompt: str, api_key: str) -> None:
    """Corre el analisis y guarda el resultado en la sesion, o muestra el error."""
    with st.spinner("Analizando comentarios…" if modo == VIVO else "Reproduciendo el análisis…"):
        try:
            resultado = analizar(batch, modo, prompt, api_key)
        except SinRespuestaGrabada:
            st.warning(
                "Este lote no tiene una respuesta grabada, así que el modo demo no puede "
                "analizarlo. Elige uno de los **ejemplos medidos** o cambia a **Gemini en vivo** "
                "en la barra lateral.",
                icon="🗂️",
            )
            return
        except LlmError as exc:
            st.error(f"No se pudo obtener respuesta de Gemini.\n\n{exc}", icon="🌐")
            return
        except ValidationError as exc:
            st.error(
                "La respuesta del modelo no cumple el esquema del reporte:\n\n"
                + _errores_legibles(exc),
                icon="🧩",
            )
            return
    st.session_state["analisis"] = {"batch": batch, "prompt": prompt, "modo": modo, "r": resultado}


# ---------------------------------------------------------------------------
# paso 2: el reporte
# ---------------------------------------------------------------------------


def banner(batch: PlaytestBatch, resultado: AnalysisResult) -> None:
    r = resultado.report
    motivos = [f"- **{h.rule_id}**: {estilos.literal(h.message)}" for h in resultado.findings]
    if r.comentarios_descartados:
        motivos.append(
            f"- Hay **{len(r.comentarios_descartados)} comentario(s) descartado(s)**: "
            "conviene confirmar que se descartaron bien."
        )
    if r.requiere_revision_humana:
        texto = "**Requiere revisión humana** antes de decidir qué se corrige."
        if motivos:
            texto += "\n\n" + "\n".join(motivos)
        st.warning(texto, icon="👀")
    else:
        st.success(
            "**Listo para entregar.** El reporte cumple todas las reglas y no pide revisión.",
            icon="✅",
        )


def metricas(resultado: AnalysisResult) -> None:
    r = resultado.report
    cols = st.columns(5)
    cols[0].metric("Comentarios", r.total_comentarios_analizados, border=True)
    cols[1].metric("Sentimiento", estilos.sentimiento(r.sentimiento_general), border=True)
    cols[2].metric("Versión", r.version_juego or "—", border=True)
    cols[3].metric("Problemas", len(r.problemas_detectados), border=True)
    cols[4].metric("Descartados", len(r.comentarios_descartados), border=True)


def pestana_problemas(resultado: AnalysisResult) -> None:
    r = resultado.report
    if not r.problemas_detectados:
        st.info("El modelo no detectó problemas en este lote.")
        return
    total = max(r.total_comentarios_analizados, 1)
    problemas = sorted(
        r.problemas_detectados,
        key=lambda p: (estilos.ORDEN_PRIORIDAD.get(p.prioridad, 9), -p.frecuencia),
    )
    for p in problemas:
        with st.container(border=True):
            st.markdown(
                f"{estilos.prioridad(p.prioridad)} {estilos.categoria(p.categoria)} "
                f"&nbsp; **{p.frecuencia}** de {r.total_comentarios_analizados} comentarios"
            )
            st.markdown(estilos.literal(p.descripcion))
            st.progress(min(p.frecuencia / total, 1.0))
            if p.fuente_predominante:
                st.caption(f"Fuente predominante: {estilos.fuente(p.fuente_predominante)}")


def pestana_evidencia(resultado: AnalysisResult) -> None:
    citas = resultado.report.comentarios_evidencia
    if not citas:
        st.info("El reporte no incluye citas.")
        return
    st.caption("Cada cita tiene que existir literalmente en el lote; el validador lo comprueba.")
    for c in citas:
        st.html(
            f'<div class="qd-cita">“{html.escape(c.texto)}”'
            f'<br><small style="opacity:.65">{html.escape(estilos.fuente(c.fuente))}</small></div>'
        )


def pestana_descartados(resultado: AnalysisResult) -> None:
    descartados = resultado.report.comentarios_descartados
    if not descartados:
        st.info("No se descartó ningún comentario.")
        return
    st.caption(
        "Nada desaparece en silencio: todo lo que el modelo no usó aparece aquí con su motivo."
    )
    for d in descartados:
        with st.container(border=True):
            st.markdown(f"{estilos.motivo(d.motivo)} &nbsp; {estilos.literal(d.texto)}")


def pestana_validacion(resultado: AnalysisResult, rules_version: str) -> None:
    reglas = rule_set(rules_version)
    st.markdown(
        f"Se aplicaron **{len(reglas)} reglas** del conjunto `{rules_version}`: "
        + ", ".join(f"`{regla.id}`" for regla in reglas)
    )
    if not resultado.findings:
        st.success("Ninguna regla encontró problemas: el reporte del modelo se entrega tal cual.")
        return

    st.warning(f"El validador encontró **{len(resultado.findings)} hallazgo(s)**.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "regla": h.rule_id,
                    "campo": h.field,
                    "severidad": str(h.severity),
                    "mensaje": h.message,
                }
                for h in resultado.findings
            ]
        ),
        hide_index=True,
    )
    st.markdown("**Lo que devolvió el modelo vs. lo que se entrega** (tras las correcciones)")
    izq, der = st.columns(2)
    with izq:
        st.caption("Crudo del modelo")
        st.json(resultado.raw_report, expanded=1)
    with der:
        st.caption("Reporte final")
        st.json(resultado.report.model_dump(), expanded=1)


def pestana_traza(resultado: AnalysisResult) -> None:
    t = resultado.trace
    if t is None:
        return
    st.caption(
        f"Ejecución `{t.run_id}` · modelo `{t.model}` · prompt `{t.prompt_version}` · "
        f"reglas `{t.rules_version}` · esquema `{t.schema_version}`"
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "paso": s.name,
                    "decisión": s.decision,
                    "duración (ms)": round(s.duration_s * 1000, 1),
                }
                for s in t.steps
            ]
        ),
        hide_index=True,
        column_config={"decisión": st.column_config.TextColumn(width="large")},
    )


def reporte(analisis: dict) -> None:
    batch: PlaytestBatch = analisis["batch"]
    resultado: AnalysisResult = analisis["r"]
    r = resultado.report

    banner(batch, resultado)
    metricas(resultado)

    with st.container(border=True):
        st.markdown("**Resumen**")
        st.markdown(estilos.literal(r.resumen_general))

    rules_version = resultado.trace.rules_version if resultado.trace else "after"
    tabs = st.tabs(
        [
            f"🧭 Problemas ({len(r.problemas_detectados)})",
            f"💬 Evidencia ({len(r.comentarios_evidencia)})",
            f"🗑️ Descartados ({len(r.comentarios_descartados)})",
            f"🛡️ Validación ({len(resultado.findings)})",
            "🧾 Traza",
            "{ } JSON",
        ]
    )
    with tabs[0]:
        pestana_problemas(resultado)
    with tabs[1]:
        pestana_evidencia(resultado)
    with tabs[2]:
        pestana_descartados(resultado)
    with tabs[3]:
        pestana_validacion(resultado, rules_version)
    with tabs[4]:
        pestana_traza(resultado)
    with tabs[5]:
        # El mismo formato que `quickdev analyze --json`.
        st.code(_como_json(resultado), language="json")

    st.download_button(
        "⬇️ Descargar reporte JSON",
        data=_como_json(resultado),
        file_name=f"quickdev_{batch.build or 'sin_build'}_{analisis['prompt']}.json",
        mime="application/json",
        type="secondary",
    )


# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="QuickDev", page_icon="🎮", layout="wide")
    st.html(estilos.CSS)
    st.html(estilos.encabezado())

    registro = PromptRegistry()
    modo, prompt, api_key = barra_lateral(registro)

    st.html(estilos.paso("Paso 1"))
    st.subheader("Elige el lote de comentarios")
    origen = st.segmented_control(
        "Origen del lote",
        [ORIGEN_EJEMPLO, ORIGEN_JSON, ORIGEN_MANUAL],
        default=ORIGEN_EJEMPLO,
        required=True,
        label_visibility="collapsed",
    )
    if origen == ORIGEN_JSON:
        batch = lote_desde_json()
    elif origen == ORIGEN_MANUAL:
        batch = lote_manual()
    else:
        batch = lote_de_ejemplo()

    if batch is not None:
        vista_previa(batch)

    falta = None
    if batch is None or batch.total == 0:
        falta = "Falta un lote con comentarios."
    elif modo == DEMO and prompt not in CRUDOS:
        falta = f"El prompt `{prompt}` no tiene respuestas grabadas para el modo demo."
    elif modo == VIVO and not api_key:
        falta = "Falta la GEMINI_API_KEY (barra lateral)."

    if st.button("🔍 Analizar", type="primary", disabled=falta is not None):
        ejecutar(batch, modo, prompt, api_key)
    if falta and batch is not None:
        st.caption(falta)

    analisis = st.session_state.get("analisis")
    # Solo se muestra si corresponde al lote y al prompt que estan en pantalla:
    # un reporte viejo debajo de un lote nuevo seria enganoso.
    if analisis and analisis["batch"] == batch and analisis["prompt"] == prompt:
        st.html(estilos.paso("Paso 2"))
        st.subheader("Reporte")
        reporte(analisis)


# Streamlit ejecuta el archivo como `__main__`; importarlo (tests) no dibuja nada.
if __name__ == "__main__":
    main()

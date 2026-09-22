# Changelog

Qué cambió en QuickDev y **cómo sabemos si mejoró**. Cada entrada enlaza el cambio con la medición
que lo respalda, o dice explícitamente que no hay ninguna.

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/). No hay versiones
publicadas: cada entrada es una rama o un hito, con su commit en `main`. Lo más reciente, arriba.

Tres reglas para leer las mediciones:

- `n = 3` corridas por eval, `temperature = 0`, `gemini-2.5-flash`, salvo que se diga otra cosa.
- **Crudo** es lo que devolvió el modelo; **corregido**, lo que entrega el sistema tras el validador.
- Una medición commiteada en `evals/resultados/` no se regenera nunca. Una corrida nueva va a su
  propio directorio.

---

## Pureza del dominio ejecutable y CI — 2026-09-22

### Medición

**Ninguna nueva, y ninguna cambiada.** Este cambio no toca `quickdev/`, ni los prompts, ni las
reglas, ni `evals/resultados/`. Verificado: `scripts/gate_baseline.py` sigue dando 7/7, y el replay
de las dos mediciones commiteadas sigue reproduciendo 12/15 y 15/15.

### Añadido

- `tests/domain/test_pureza.py`: la regla estructural del proyecto —nada de `quickdev/domain/`
  importa infraestructura— deja de ser un `grep` en un documento y pasa a comprobarse en cada
  `pytest`. Lee los imports con `ast` y exige que cada uno sea stdlib sin efectos, `pydantic` o
  `quickdev.domain`.

  Por qué el AST y no el `grep` de `docs/arquitectura.md`: ese grep busca cinco nombres escritos a
  mano (`google|pandas|requests|os|pathlib`), así que dejaba pasar `import httpx`, `import socket`
  y, sobre todo, `from quickdev.adapters import GeminiAdapter` — la única violación que la
  arquitectura no podría sobrevivir, porque invierte la dirección de las dependencias. Es el mismo
  argumento del proyecto aplicado a sí mismo: una instrucción en un documento no es una garantía;
  una comprobación que corre sí ([ADR-0001](docs/adr/0001-arquitectura-hexagonal.md)).

- `.github/workflows/ci.yml`: `ruff`, `pytest`, `scripts/gate_baseline.py` y el replay de las dos
  mediciones, en cada push a `main` y en cada PR, sobre Python 3.12 y 3.14. **No necesita
  `GEMINI_API_KEY` ni gasta cuota**: la suite deselecciona `-m llm` por defecto y los evals corren
  con `FakeLlm`. Varios documentos ya decían que el pipeline "corre en CI sin red"; hasta ahora no
  había CI que lo hiciera.

### Cambiado

- `docs/arquitectura.md` (sección 7): la comprobación de pureza documenta el test y conserva el
  `grep` como atajo, con sus dos límites escritos.
- El contador de la suite sube a 462 en `README.md` y `docs/arquitectura.md`: los 12 tests
  nuevos de `test_pureza.py`.

---
## `feature/web-streamlit` — 2026-09-22 · interfaz web

### Medición

**Ninguna nueva.** La web es otra superficie como la CLI: compone `AnalyzeBatch` con
`construir_analisis` y no toca prompts, reglas ni adaptadores. En modo demo reproduce las mismas
respuestas grabadas que `quickdev demo`.

### Añadido

- `quickdev/web/`: interfaz Streamlit (`streamlit run quickdev/web/app.py`). Lote desde un ejemplo
  medido, un JSON subido o comentarios escritos a mano; modo demo sin API key o Gemini en vivo;
  reporte con banner de revisión humana, métricas, problemas, evidencia, descartes, hallazgos del
  validador (crudo vs. corregido), traza y descarga del JSON.
- `.streamlit/config.toml`: tema claro y oscuro, fuentes Inter y JetBrains Mono.
- Extra opcional `web` en `pyproject.toml` (`streamlit==1.64.0`, fijado como el resto).
- `tests/web/test_app.py`: 8 tests con `AppTest`, sin red; se saltan si Streamlit no está instalado.

## `core/jose` — 2026-09-14 · prompts, CLI, documentación y demo

### Medición

**Ninguna nueva.** Esta rama no cambia lo medido, y está verificado:

- `baseline` y `after` se sirven desde `prompts/*.md` con el mismo `sha256` que el texto legacy, y
  el input es byte a byte el que recibió el modelo según `crudo.json`
  (`tests/application/test_prompting.py`).
- El replay del baseline sigue reproduciendo las tasas y aserciones commiteadas
  (`tests/evals/test_replay_baseline.py`), el de after da 15/15 y `scripts/gate_baseline.py`, 7/7.

### Añadido

- `prompts/baseline.md` y `prompts/after.md`: los prompts medidos, congelados con su `sha256`, y
  `PromptRegistry` para leerlos ([ADR-0011](docs/adr/0011-prompts-como-archivos-congelados.md)).
- **`prompts/v2.md`, SIN MEDIR.** Hipótesis: enviar los comentarios como array JSON evita que una
  comilla o un salto de línea rompan el formato numerado del input. Cómo se sabrá:
  `quickdev eval --prompt v2 --n 10` contra `evals/resultados/after/`. No es el default.
- `quickdev` CLI: `analyze`, `eval` y `demo`. `quickdev demo` corre sin API key y sin red.
- `docs/historia/`: la narrativa del notebook original, migrada sin editar.
- `README.md`, `docs/adr/README.md`, ADR-0010 y ADR-0011.
- `nbstripout` como filtro de git para el notebook.

### Cambiado

- **Contrato:** `PromptProvider.build_payload(batch)` pasa a `build_payload(batch, version)`, porque
  la forma del payload es parte de cada versión de prompt. Afecta a `AnalyzeBatch`, al runner y a
  los dobles de test.
- La versión de reglas por defecto de una corrida la declara el prompt (`v2` → `after`), en vez de
  suponer que se llama igual.
- `QuickDev_01.ipynb`: de 40 celdas con todo el sistema a 5 celdas sin lógica
  ([ADR-0010](docs/adr/0010-notebook-como-demo-delgada.md)). Deja de estar exento de `ruff`.
- `docs/arquitectura.md`, `evals/README.md` y `MAKERS_REVIEW.md`: actualizados; lo obsoleto se
  marca, no se borra.

### Eliminado

- `evals/prompts_legacy.py`, el puente temporal que dejó `core/miguel`.

### Corregido

- **Un replay podía producir una medición falsa.** `python -m evals --modo v2 --replay
  evals/resultados/after/crudo.json` salía con código 0 y un diagnóstico de **0/15** para un prompt
  que nunca se midió. Ahora falla antes de correr si el archivo no tiene ninguna corrida con esa
  forma de input.
- Una corrida con payload no-string no se habría podido reproducir después: el runner guardaba
  `input = None`. Grabar y reproducir usan ahora la misma clave (`FakeLlm.key_for_payload`).

---

## `core/miguel` — 2026-09-14 · puertos, adaptadores y evals ([`a706440`](https://github.com/david181222/QuickDev/commit/a706440))

### Medición

**Replay del baseline**, sin API: [`evals/resultados/2026-09-14-baseline-baseline/`](evals/resultados/2026-09-14-baseline-baseline/diagnostico.md).
Reproduce **idéntico** el comportamiento observado: 12/15, cada aserción fallida corrida a corrida
y las 7 regresiones. Lo que cambia son **tres respuestas derivadas** del diagnóstico, que estaban mal
inferidas ([ADR-0008](docs/adr/0008-correcciones-al-diagnostico.md)):

| Pregunta | Antes | Ahora | Por qué |
| --- | --- | --- | --- |
| ¿La tool devolvió mal? (happy path, ambiguo, adversarial) | SÍ | NO | eran reintentos por rate limit que acabaron bien |
| ¿Elegimos mal el modelo? (los cinco) | SÍ o NO | SIN DATO | con n = 3 no se separa un flake de un defecto |
| ¿Faltó contexto? | NO | NO, marcada como derivada | no es independiente de "¿Falló el prompt?" |

### Añadido

- `GeminiAdapter` con `response_schema` del proveedor ([ADR-0009](docs/adr/0009-structured-output-del-proveedor.md), **sin medir**).
- `RetryingLlm`, `CachingLlm` y `FakeLlm` como decoradores del puerto ([ADR-0006](docs/adr/0006-puerto-llm-y-adaptadores-decorados.md)).
- `RunManifest` y un directorio por corrida ([ADR-0007](docs/adr/0007-resultados-versionados-y-manifiesto.md)).
- `tests/evals/test_replay_baseline.py`: la puerta final de la migración como test.

### Cambiado

- `evals/motor.py` (690 líneas) y `evals/casos.py` se reparten en `cases`, `regressions`, `runner`,
  `diagnosis` y `reporting`. La CLI pasa a `python -m evals`.
- `n` por defecto: de 3 a 10.

### Corregido

- Volver a correr los evals **borraba la medición anterior** (`motor.py:566`).
- Un 400 o un 401 dormía 135 s antes de rendirse: los errores terminales ya no se reintentan.
- Una aserción con un bug contaba como fallo del modelo: ahora es un tercer estado, `ERROR`.
- En replay, si faltaba una corrida, `n` se encogía en silencio.

---

## `core/edwin` — 2026-09-14 · dominio y capa de aplicación ([`343efe3`](https://github.com/david181222/QuickDev/commit/343efe3))

### Medición

**Equivalencia con el validador original**, sin API, sobre los 37 casos del repo (7 regresiones y 30
corridas guardadas) y las dos versiones de reglas: **72/74** listas de hallazgos idénticas, **14/14**
veredictos preservados y **una** divergencia documentada
([ADR-0004](docs/adr/0004-detectar-vs-reparar.md)). Gate: 7/7.

### Añadido

- Nueve reglas, una clase por regla; `baseline` y `after` como composiciones ([ADR-0003](docs/adr/0003-una-regla-una-clase.md)).
- `Validator` y `RepairPolicy` separados ([ADR-0004](docs/adr/0004-detectar-vs-reparar.md)).
- `AnalyzeBatch` como secuencia explícita de pasos con `Trace`.
- `DetectedIssue.evidencia_idx`, aditivo y opcional ([ADR-0005](docs/adr/0005-evidencia-por-indice.md); la regla que lo usa, **sin medir**).

### Corregido

- `QuotesAreLiteral` aceptaba una cita que envolvía un comentario real con texto inventado
  (`real in t`). Se midió antes de arreglarlo: sobre las 132 citas de los 37 casos, el arreglo no
  cambia ningún resultado.

---

## Paso 0 — 2026-09-14 · contratos y andamiaje ([`c409cf9`](https://github.com/david181222/QuickDev/commit/c409cf9))

### Añadido

- `pyproject.toml` con dependencias fijadas con `==`, el árbol del paquete y los contratos
  compartidos (`FeedbackReport`, `Rule`, `LlmPort`, `Trace`, `AnalysisResult`, `Settings`).
- `scripts/gate_baseline.py`, la puerta de aceptación de las tres ramas.
- ADR-0001 y ADR-0002.

### Corregido

- `.gitignore` ignoraba en silencio `.env.example`.
- Los 8 campos del reporte no eran requeridos: un `comentarios_descartados` ausente se volvía `[]`.

### Medición

Ninguna. Gate 7/7, igual que antes.

---

## Mediciones baseline y after — 2026-08-21 ([`418deff`](https://github.com/david181222/QuickDev/commit/418deff))

Primer harness de evals (`evals/motor.py`) y las dos mediciones que siguen siendo la línea base.

### Medición

| Eval | [baseline](evals/resultados/baseline/diagnostico.md) | [after](evals/resultados/after/diagnostico.md) |
| --- | :-: | :-: |
| Happy path | 3/3 | 3/3 |
| Input incompleto | 3/3 | 3/3 |
| Input ambiguo | 3/3 | 3/3 |
| Input adversarial | 3/3 | 3/3 |
| Edge case de versión | **0/3** | **3/3** |
| **Total** | **12/15** | **15/15** |
| Regresiones | 5 PASS / 2 FAIL | 7 PASS |

### Cambiado (baseline → after)

Dos hipótesis, cada una con cambio en el prompt **y** en el validador:

1. **La versión.** Con dos versiones en el input (la build `v0.8.2` y una `v0.5` citada por un
   jugador), la regla "que aparezca literalmente" no desempata. Crudo baseline: `v0.5` en 2 de 3
   corridas, y el validador no lo atrapó. Cambio: el prompt fija la versión a la build de la
   primera línea y la regla `VersionIsAnalyzedBuild` lo verifica. Crudo after: `v0.8.2` en 3/3.
2. **La revisión humana.** Escrita como juicio, el modelo la dejó en `false` en 6 de 15 corridas
   del baseline; el código la forzó en 5 y **en una salió sin revisión**. Cambio: una lista cerrada
   de condiciones en el prompt y dos reglas nuevas. Crudo after: marcada por el modelo en 15/15.

**Límite de la medición:** como cada salto cambió prompt y validación a la vez, la mejora no se
puede atribuir a uno solo. Las 2 regresiones que fallan en baseline son el falso positivo
`VersionIsNotNull`, conservado a propósito.

---

## Revisión de Makers — 2026-08-13 ([`9537436`](https://github.com/david181222/QuickDev/commit/9537436))

### Añadido

- `evals/quickdev_regression_cases.csv` y `evals/README.md`: cinco escenarios de regresión en prosa.
- `MAKERS_REVIEW.md`.

### Medición

**4/5** en la tabla de pruebas adversariales del notebook (Parte 7): cinco casos, **una corrida
cada uno**, y fallaba el caso `normal`. Es una medición distinta y más pequeña que las de
`evals/resultados/`, y ya no existe: el notebook dejó de contener pruebas. No es comparable con
12/15 ni con 15/15.

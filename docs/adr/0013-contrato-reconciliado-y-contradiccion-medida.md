# ADR-0013 · El contrato se reconcilia con el código; lo medido conserva su contradicción

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-19
- **Decide:** equipo (`prep/sustentacion`)
- **Afecta a:** `evals/contract_frozen.json`, `tests/application/test_prompting.py`,
  `tests/domain/test_contrato_congelado.py`, el docstring de `quickdev/application/prompting.py`.
  **No** toca `prompts/*.md` ni `prompts/contexto.json`.

## Contexto

`evals/contract_frozen.json` lo generó un modelo en la Parte 4 del notebook original
([historia](../historia/caso-de-uso-y-posicionamiento.md)), entró al repo el 2026-08-21 (`2b55e8c`)
y no había cambiado desde entonces. Los prompts `baseline` y `after` se renderizaban a partir de él:
el `ai_job` se interpolaba en el texto del prompt, y `human_decision` + `system_validations` viajaban
en el payload como `context`. El ADR-0011 congeló los prompts ya renderizados en `prompts/*.md` y
copió ese `context` a `prompts/contexto.json` precisamente para que el contrato se pudiera
reconciliar sin tocar lo medido. Nadie lo había hecho.

La fuente de verdad para reconciliarlo es el código: `quickdev/domain/models.py` (tipos y
vocabularios cerrados) y el conjunto de reglas `after` (`quickdev/domain/rules/registry.py`), con la
`RepairPolicy` de `quickdev/domain/validation.py`.

## Las contradicciones encontradas

Se revisó cada campo del contrato contra el código. Las cuatro primeras eran conocidas; las demás
salieron de la revisión.

| # | Dónde | El contrato decía | El código hace |
| --- | --- | --- | --- |
| 1 | `system_validations` | fuentes permitidas "ej. 'Discord', 'Google Forms', 'Mensaje Directo'" | `Fuente` = `discord \| steam \| encuesta \| red_social`. 'Google Forms' y 'Mensaje Directo' no existen |
| 2 | `system_validations` | `version_juego` debe aparecer "literalmente en al menos uno de los comentarios" | `VersionIsAnalyzedBuild`: es la build declarada, o null si no hay. Una versión citada en un comentario nunca cuenta |
| 3 | `ai_job` | "Extraer la versión del juego mencionada literalmente en los comentarios." | es justo el trabajo que el arreglo del edge case le quitó al modelo |
| 4 | `output_fields.version_juego` | "la versión mencionada más frecuentemente o más relevante en los comentarios" | la misma contradicción que el punto 2 |
| 5 | `input_required` | "Tipo de jugador (opcional)", "Tiempo jugado (opcional)" | `PlaytestComment` solo tiene `fuente` y `texto`. Si llegan esos campos, Pydantic los descarta sin avisar |
| 6 | `input_required` | "Versión de la build", como requerida | `PlaytestBatch.build` es opcional: `None` significa "build no especificada" |
| 7 | `ai_job` | detectar el sentimiento "de cada comentario" | el reporte solo tiene `sentimiento_general`, del lote |
| 8 | `output_fields.problemas_detectados` | `categoria` como string libre; sin `fuente_predominante` ni `evidencia_idx` | `Categoria` es una lista cerrada de 8; `DetectedIssue` tiene `fuente_predominante` (opcional) y `evidencia_idx` (opcional, esquema v1.1) |
| 9 | `output_fields.requiere_revision_humana` | un juicio: "si el reporte contiene ambigüedades o problemas" | `after` lo convirtió en una lista cerrada de condiciones, y el código lo fuerza ante cualquier descarte, más de una build o cualquier hallazgo. La redacción como juicio es la que el baseline midió inestable |
| 10 | `system_validations` | no mencionaba ninguna validación de revisión humana | `AnyDiscardRequiresReview`, `MultipleBuildsRequireReview` y la regla global de `RepairPolicy` |
| 11 | `output_fields` | sin los límites de `resumen_general` (400) ni de `descripcion` (200); `fuente` de la evidencia como string obligatorio | los límites están en el tipo; `QuotedComment.fuente` es `str \| None`, texto libre |

## Decisión

**1. El contrato se corrige.** `evals/contract_frozen.json` pasa a describir lo que el código acepta,
devuelve y verifica. Las listas cerradas se escriben `a | b | c`, la misma notación que usan los
esquemas de los prompts. **No se renombra:** el nombre es histórico y lo citan ADRs, `historia/` y
docstrings; la copia congelada de lo medido ya tiene su sitio, `prompts/contexto.json`.

Las secciones narrativas (`jtbd`, `problem_thesis`, `current_alternative`, `success_metric`,
`riskiest_assumption`...) no se tocan: describen el problema y la hipótesis del producto, no lo que
el código acepta. Que `current_alternative` diga "Google Forms" es correcto: es donde vive hoy el
feedback. Dos afirmaciones de `jtbd` no las cumple el sistema y se anotan en vez de reescribirse:
"cientos de comentarios" (el eval más grande tiene 14, ver límites del README) y "saber si lo que se
corrigió en la build anterior efectivamente dejó de aparecer" (el sistema analiza un lote; no
compara builds).

**2. Lo medido no se corrige.** `prompts/baseline.md`, `after.md`, `v2.md` y `prompts/contexto.json`
se quedan como están. Son el registro de lo que el modelo vio, y corregirlos haría que las
mediciones de `evals/resultados/` describieran un texto que el modelo nunca recibió.

**3. El test que igualaba contrato y contexto cambia de premisa.**
`test_prompting.py::test_el_contexto_es_el_que_recibio_el_modelo_al_medir` exigía que el `context`
del payload fuera igual al contrato. Al reconciliar, falló a propósito: "contrato == contexto
medido" dejó de ser cierto. Ahora compara el payload con `prompts/contexto.json` y fija con un
sha256 que esa copia es, byte a byte, el `context` que el harness viejo armaba con el contrato de
`418deff`, el commit de las mediciones. Sin el hash, el test sería tautológico: `build_payload` lee
ese mismo archivo.

**4. Un test impide que vuelvan a divergir.** `tests/domain/test_contrato_congelado.py` exige que
cada lista cerrada de las secciones normativas del contrato sea **exactamente** uno de los cinco
vocabularios de `models.py` (`Fuente`, `Categoria`, `Prioridad`, `Sentimiento`, `MotivoDescarte`),
que los cinco estén declarados completos, y que 'Google Forms' y 'Mensaje Directo' no aparezcan.
Contra el contrato anterior falla en 7 de sus 8 casos; contra el reconciliado pasa.

## La contradicción que quedó dentro de lo medido

Esto es lo que el modelo recibió al medir `after`, y no se puede cambiar:

- **`prompts/after.md`, línea 16** (`ai_job`): "Extraer la versión del juego mencionada
  literalmente en los comentarios."
- **Líneas 23-26 del mismo prompt:** "version_juego es SIEMPRE esa build y ninguna otra [...] Las
  versiones que los jugadores mencionen dentro de sus comentarios NUNCA van en version_juego".
- **Línea 53** (esquema): `version_juego` es "la version mencionada literalmente en el input", la
  regla del baseline, que no desempata cuando hay dos.
- **Línea 55** (esquema): `requiere_revision_humana` es "true si hay ambiguedad, datos faltantes
  o [...]", el juicio que las líneas 34-35 dicen que no es ("No es un juicio general [...] es esta
  lista").
- **`prompts/contexto.json`** (el `context` del payload): las fuentes 'Discord', 'Google Forms' y
  'Mensaje Directo', y la validación de "versión literal en algún comentario". Son los puntos 1 y 2.

El mismo prompt da instrucciones opuestas sobre lo que mide el edge case. **Y aun así `after` sacó
15/15.** En el output crudo de las 15 corridas (`evals/resultados/after/crudo.json`): `version_juego
= v0.8.2` en las 3 del edge case, `requiere_revision_humana = true` en las 15, todas las fuentes en
los valores del enum y en minúscula, y **cero hallazgos** del validador. El modelo siguió la regla
explícita y específica, no el `ai_job`, ni la descripción del esquema, ni el `context`.

Lo que eso dice y lo que no: dice que, en esas 3 corridas por caso, con ese modelo y
`temperature = 0`, la regla explícita dominó. No dice que la contradicción sea inofensiva: con n = 3
no se sabe cuánto cuesta en estabilidad ni si otro modelo la resolvería igual. Es una razón para
quitarla en el próximo prompt, no para dejarla.

## `v2` la hereda

`prompts/v2.md` es `after` con dos bloques de reglas reescritos y nada más, y
`test_v2_solo_cambia_las_reglas_que_citaban_la_primera_linea` lo hace cumplir. Así que `v2` tiene
el mismo `ai_job` (línea 16), las mismas descripciones de esquema (líneas 53 y 55) y recibe el
mismo `prompts/contexto.json`.

**Quien mida `v2` o un `v3` tiene que quitar la contradicción antes y declararlo como uno de sus
cambios.** Tres consecuencias prácticas:

- Quitarla toca líneas que ese test protege, a propósito: el test cambia en el mismo commit.
- Una medición que cambie el formato del input **y** quite la contradicción compara dos cambios
  contra `after`. O se declaran los dos, o se miden por separado.
- El `context` sale de `prompts/contexto.json` para todas las versiones. Quitar la contradicción del
  `context` exige que una versión nueva pueda declarar el suyo, y eso es un cambio de
  `PromptRegistry` que hoy no existe.

## Consecuencias

- El contrato describe lo que el código hace, y el límite "`contract_frozen.json` contradice al
  código" deja de ser cierto. Lo sustituye otro: **lo medido contiene una contradicción**, y está
  documentada aquí.
- El test cubre los **valores cerrados**, no la semántica. Que `version_juego` sea la build
  declarada, o qué fuerza la revisión humana, está escrito en el contrato pero lo comprueban las
  reglas y sus tests, no un test del contrato.
- Los ADR-0010 y 0011 y `docs/historia/` siguen diciendo que el contrato contradice al código. Son
  registro de lo que era cierto cuando se escribieron y no se editan.

## Alternativas descartadas

**Corregir también `prompts/after.md` y `contexto.json`.** Dejaría el repo "coherente" a costa de
que `evals/resultados/after/` describa un prompt que el modelo nunca vio. Además rompe el sha256 que
el ADR-0011 fija, que existe justo para impedir esto.

**Renombrar el archivo a algo como `contrato.json`**, ya que ha dejado de estar congelado. Rompe
referencias en ADRs, `historia/` y docstrings para ganar solo precisión en el nombre, y la copia
congelada de verdad ya existe.

**Dejar el contrato como estaba y documentar la contradicción.** Es lo que se había hecho: una línea
en los límites del README. El contrato es lo que alguien nuevo lee para saber qué acepta el
sistema, y le estaba diciendo que acepta 'Google Forms'.

**Un test que compare el contrato entero con el código**, semántica incluida. Exigiría interpretar
prosa. Los valores cerrados son la parte del contrato que se puede comparar sin interpretar, y es
donde estaba la divergencia más visible.

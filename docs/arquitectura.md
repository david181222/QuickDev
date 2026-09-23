# Arquitectura de QuickDev

Documento de arquitectura del proyecto. Describe **lo que está en `main`**, no un
plan: cada archivo que se menciona existe, y lo que todavía es un stub está
marcado como tal.

Verificado contra `main` con las tres ramas de la migración mergeadas (`core/edwin`,
`core/miguel` y `core/jose`) · 14 sep 2026

---

## 1. La tesis, que ordena todo lo demás

> **El modelo interpreta lenguaje. El código verifica hechos.**

El modelo clasifica comentarios por tema, los agrupa, resume y detecta tono.
Código determinista comprueba los conteos contra `len()`, los enums contra listas
cerradas, y que cada cita exista literalmente en el lote.

Esa frase no es un eslogan: es el criterio con el que se decide, ante cada
requisito nuevo, de qué lado de la frontera va. Y es la razón de que la
arquitectura sea hexagonal — un dominio puro rodeado de adaptadores es
exactamente la forma de código que esa frontera pide.

**Una instrucción en el prompt no es una garantía. Una validación posterior sí.**
El prompt pide al modelo que no invente números; el validador lo comprueba. Las
dos cosas hacen falta, y solo la segunda es verificable.

---

## 2. El flujo de una ejecución

```mermaid
flowchart LR
    LOTE["Lote de playtest<br/>comentarios + build analizada"]

    subgraph APP["application/ - ordena los pasos"]
        direction TB
        PROMPT["1 - PromptRegistry<br/>prompts/*.md versionados"]
        PARSE["3 - Parseo a FeedbackReport<br/>extra = forbid"]
    end

    subgraph INFRA["adapters/ - unico lugar con SDK"]
        direction TB
        GEM["2 - GeminiAdapter<br/>response_schema"]
    end

    subgraph DOM["domain/ - sin modelo, sin red, sin I/O"]
        direction TB
        VAL["4 - Validator<br/>RuleSet baseline o after"]
        REP["5 - RepairPolicy"]
    end

    OUT["FeedbackReport validado<br/>+ Trace de la ejecucion"]
    HUM{"revision humana?"}
    DEV["El desarrollador revisa<br/>y confirma"]
    FIN["Reporte entregado"]

    LOTE --> PROMPT
    PROMPT -->|"cruza el puerto LlmPort"| GEM
    GEM --> PARSE
    PARSE --> VAL
    VAL --> REP
    REP --> OUT
    OUT --> HUM
    HUM -->|si| DEV
    HUM -->|no| FIN
    DEV --> FIN
```

Los números marcan una secuencia real: hoy los pasos son fijos y en ese orden.
`LlmPort` aparece como **etiqueta de la flecha, no como nodo**, porque no es un
paso del flujo: es la interfaz que el adaptador implementa y la frontera que la
llamada cruza. La relación "implementa" se ve en el diagrama de capas, abajo.

Tres cosas que este diagrama afirma y que conviene leer despacio:

**El modelo entra una sola vez, y entra por un puerto.** No hay una segunda
llamada para "revisar" lo que dijo la primera. Eso hace el sistema barato y
predecible, y es una decisión consciente: hoy QuickDev **no es un agente**, es una
extracción estructurada con validación posterior. Para este caso de uso eso es lo
correcto — no hay decisiones encadenadas ni herramientas que invocar.

**La validación ocurre después del modelo y sin él.** `Validator` no puede
llamar a Gemini ni siquiera si quisiera: `domain/` no importa nada de
infraestructura, y hay una comprobación que lo verifica (sección 7).

**El rombo no es decorativo.** `requiere_revision_humana` lo puede encender el
modelo, pero el código lo **fuerza** cuando encuentra cualquier hallazgo. Un
reporte que afirma algo falso nunca sale sin pasar por una persona.

---

## 3. Las capas y la dirección de las dependencias

Esta es la regla estructural del proyecto: **las flechas apuntan siempre hacia
adentro**. Nada de `domain/` sabe que existen los adaptadores.

```mermaid
flowchart TB
    subgraph BORDE["Lo que cambia - el borde"]
        CLI["cli.py"]
        NB["QuickDev_01.ipynb<br/>demo"]
        EV["evals/"]
    end

    subgraph ADAPT["adapters/ - unico lugar con SDK"]
        GEM["gemini.py"]
        FAKE["fake.py"]
        RET["retry.py"]
        CACHE["cache.py"]
    end

    APP["application/<br/>AnalyzeBatch, prompting"]
    PORTS["ports/<br/>LlmPort, LlmRequest, LlmResponse"]
    OBS["observability/<br/>Trace, RunManifest"]
    CONF["config.py<br/>Settings"]

    subgraph CORE["domain/ - el nucleo, puro"]
        MOD["models.py<br/>el contrato"]
        RULES["rules/<br/>una regla, una clase"]
        VALID["validation.py<br/>Validator, RepairPolicy"]
    end

    CLI --> APP
    NB --> APP
    EV --> APP
    CLI -->|compone| ADAPT
    EV -->|compone| ADAPT
    ADAPT --> CONF
    OBS --> PORTS
    APP --> PORTS
    APP --> CORE
    APP --> OBS
    APP --> CONF
    CONF --> RULES
    RULES --> MOD
    VALID --> MOD
    VALID --> RULES
    GEM -.->|implementa| PORTS
    FAKE -.->|implementa| PORTS
    RET -.->|implementa| PORTS
    CACHE -.->|implementa| PORTS
```

Las flechas continuas son **dependencias** y las punteadas, **implementaciones**. Las marcadas
`compone` son el único sitio donde el borde elige adaptador: `quickdev/cli.py` y `evals/runner.py`
deciden si hay `GeminiAdapter` o `FakeLlm` debajo, y nada por dentro se entera.
Que las dos apunten hacia dentro es el principio de inversión de dependencias
dibujado: ni el caso de uso depende del SDK, ni el SDK del caso de uso — los dos
dependen de la misma abstracción, `LlmPort`. Eso es lo que permite componer
`CachingLlm(RetryingLlm(GeminiAdapter()))` en producción y `FakeLlm()` en los
tests, sin que `application/` ni `domain/` se enteren.

El grafo de imports real se puede extraer del código y coincide con este dibujo:

| Módulo | Importa de `quickdev` |
| --- | --- |
| `domain/models.py` | — *nada, es la hoja* |
| `domain/rules/base.py` | `domain.models` |
| `domain/rules/counts.py` | `domain.models`, `domain.rules.base` |
| `domain/rules/citations.py` | `domain.models`, `domain.rules.base` |
| `domain/rules/versioning.py` | `domain.models`, `domain.rules.base` |
| `domain/rules/review.py` | `domain.models`, `domain.rules.base`, `domain.rules.versioning` |
| `domain/rules/registry.py` | `domain.rules.base` y los cuatro módulos de reglas |
| `domain/validation.py` | `domain.models`, `domain.rules.base` |
| `ports/llm.py` | — *nada* |
| `observability/trace.py` | — *nada* |
| `observability/manifest.py` | `ports.llm` |
| `config.py` | `domain.rules.registry` |
| `application/prompting.py` | `domain.models` |
| `application/types.py` | `domain.models`, `domain.rules.base`, `observability.trace` |
| `application/analyze_batch.py` | ocho módulos: `application.prompting`, `application.types`, `config`, `domain.models`, `domain.rules.base`, `domain.validation`, `observability.trace`, `ports.llm` |
| `adapters/cache.py`, `fake.py`, `retry.py` | `ports.llm` |
| `adapters/gemini.py` | `ports.llm`, `config` |
| `cli.py` | `adapters`, `application`, `config`, `domain`, `ports` — es composición, no lógica |

Tres detalles de ese grafo que no son accidentes:

**`ports/llm.py` no depende del dominio.** El puerto devuelve un `dict`, no un
`FeedbackReport`; el parseo al modelo de dominio ocurre en `application/`. Eso
tiene dos consecuencias buenas: los adaptadores se pueden escribir sin esperar a
que el dominio esté listo, y el JSON crudo del modelo se conserva intacto, que es
lo que los evals necesitan para distinguir "falló el prompt" de "faltó
validación".

**`application/analyze_batch.py` es el único que conoce el orden completo del
flujo**, y por eso importa ocho módulos. Todo lo demás conoce solo su vecino.
`cli.py` importa todavía más, pero no decide nada: solo elige el adaptador y
compone las piezas. Si alguna vez decide algo sobre el reporte, está en el sitio
equivocado.

**`config.py` importa del dominio, y en esa dirección está bien.** Depende de
`domain.rules.registry` para validar al arrancar que el `rules_version` pedido
existe, en vez de reventar con un `KeyError` a mitad de una corrida de evals que
ya gastó llamadas a la API. La flecha va hacia adentro, que es la regla.

---

## 4. La frontera: dónde está cada cosa

Makers pidió documentar "la frontera entre notebook, motor de evals, casos,
outputs y reportes". Esta es la traducción de ese vocabulario al repo actual.

| Nombre en el diagrama de Makers | Dónde vive hoy | Estado |
| --- | --- | --- |
| `EntradaProyecto` | `PlaytestBatch` en `quickdev/domain/models.py` | implementado |
| `AgenteQuickDev` | `AnalyzeBatch` (`application/`) + `GeminiAdapter` (`adapters/`) | implementado |
| `ContratoSalida` | `FeedbackReport`, esquema `v1.1` | implementado |
| `MotorEvals` | `evals/runner.py`, `diagnosis.py`, `reporting.py` (antes `evals/motor.py`) | implementado |
| `CasosEval` | `evals/cases.py` (5 evals) y `evals/regressions.py` (7 regresiones) | implementado |
| `ReporteBaseline` | `evals/resultados/baseline/` | medido y congelado |
| `ReporteAfter` | `evals/resultados/after/` | medido |

### El notebook ya no es el sistema

Este es el cambio más importante respecto de la versión que Makers revisó.
`QuickDev_01.ipynb` contenía el producto: el esquema, el validador, los prompts y
las pruebas. Eso producía un problema medible: `validate_output`, `OUTPUT_SCHEMA`
y `build_input` estaban escritos **dos veces**, en el notebook y en
`evals/motor.py`, y habían divergido. La copia del notebook era la vieja, con un
falso positivo que la otra ya tenía corregido. La respuesta a "¿el validador
atrapa el edge case de versión?" dependía de qué archivo abrieras.

Ahora el paquete `quickdev/` es la única fuente, y el notebook es una **demo
narrada** de cinco celdas que importan `quickdev` y muestran el flujo, sin lógica
propia ([ADR-0010](adr/0010-notebook-como-demo-delgada.md)). Lo mismo, en terminal,
es `quickdev demo`. El razonamiento que vivía en las celdas del notebook está en
[`historia/`](historia/README.md).

---

## 5. Los evals: dónde están los casos y dónde quedan los resultados

```mermaid
flowchart LR
    CASES["evals/cases.py<br/>5 EvalCase"]
    REGR["evals/regressions.py<br/>7 regresiones, sin modelo"]
    RUNNER["evals/runner.py<br/>corre AnalyzeBatch n veces"]
    DIAG["evals/diagnosis.py<br/>las 7 preguntas"]
    REPORT["evals/reporting.py<br/>CSV, MD, JSON + manifiesto"]
    CRUDO["resultados/*/crudo.json<br/>input y output de cada corrida"]
    BASE["resultados/baseline/<br/>12/15 - referencia congelada"]
    AFTER["resultados/after/<br/>15/15"]
    NUEVA["resultados/fecha-prompt-reglas/<br/>una carpeta por corrida"]
    GATE["scripts/gate_baseline.py<br/>puerta de aceptacion"]

    CASES --> RUNNER
    RUNNER --> DIAG
    DIAG --> REPORT
    REGR --> REPORT
    REPORT --> NUEVA
    BASE --> CRUDO
    AFTER --> CRUDO
    CRUDO -->|"FakeLlm: replay sin API"| RUNNER
    REGR --> GATE
    BASE --> GATE
```

### Qué hay en cada carpeta de resultados

`baseline/` y `after/` contienen la misma estructura de cuatro archivos:
`resultados.csv` (una fila por corrida), `diagnostico.md` (las 7 preguntas
respondidas por eval), `crudo.json` (input y output de cada corrida) y
`regresion.csv`. Son las dos mediciones históricas y no se regeneran.

Cada corrida nueva escribe en su propio directorio,
`resultados/<fecha>-<prompt>-<reglas>/`, con un quinto archivo, `manifiesto.json`,
que estampa versiones, modelo, `git_sha` y latencia agregada
([ADR-0007](adr/0007-resultados-versionados-y-manifiesto.md)).
`2026-09-14-baseline-baseline/` es el replay del baseline hecho al migrar el harness.

Son dos mediciones reales, no ejemplos:

| | baseline | after |
| --- | --- | --- |
| Happy path | 3/3 | 3/3 |
| Input incompleto | 3/3 | 3/3 |
| Input ambiguo | 3/3 | 3/3 |
| Input adversarial | 3/3 | 3/3 |
| Edge case de versión | **0/3** | **3/3** |
| **Total** | **12/15** | **15/15** |
| Regresiones deterministas | 5 PASS / 2 FAIL | 7 PASS |

El salto de `0/3` a `3/3` en el edge case es la mejora medida del proyecto. El
caso: la build analizada es `v0.8.2` pero un jugador cita la `v0.5` dentro de su
comentario. Las dos versiones aparecen literalmente en el input, así que la regla
del prompt ("la versión debe aparecer literalmente") no desempata. Se arregló con
dos cambios a la vez —una regla nueva en el validador y una instrucción más
precisa en el prompt—, y eso hay que decirlo: no fue solo prompt.

### `crudo.json` es la pieza que hace los evals reproducibles

Guarda el input y el output de cada corrida — 15 por medición. `FakeLlm` los
reproduce, y con eso el pipeline completo corre en CI **sin red, sin API key y
sin cuota**:

```bash
.venv/bin/quickdev eval --prompt after --replay evals/resultados/after/crudo.json
```

No es un comando que alguien tenga que acordarse de correr:
`tests/evals/test_replay_baseline.py` lo hace en cada `pytest` y compara tasas y
aserciones contra el `diagnostico.md` commiteado. Lo único que difiere son tres
respuestas **derivadas** que estaban mal inferidas, con su antes y después en
[ADR-0008](adr/0008-correcciones-al-diagnostico.md).

El replay busca cada corrida por su input, así que solo reproduce lo que se midió
con esa misma forma de payload. El prompt `v2` envía los comentarios como array
JSON y por eso no tiene replay hasta que se mida contra la API
([ADR-0011](adr/0011-prompts-como-archivos-congelados.md)); pedirlo falla antes de
correr, en vez de producir un diagnóstico falso de 0/15.

### La puerta de aceptación

`scripts/gate_baseline.py` compara las regresiones deterministas contra
`baseline/regresion.csv` y sale con código 1 si algo difiere. Es lo que prueba
que un refactor no cambió el comportamiento medido. Hoy da **7/7**: 5 PASS y los
2 FAIL deliberados, que existen para exponer el falso positivo del validador
baseline.

Vive en `scripts/` y no en `evals/` porque las tres ramas de trabajo la necesitan,
incluida la que se mergea antes de que exista el harness nuevo.

---

## 6. Estado real: qué está construido y qué falta

| Archivo | Estado |
| --- | --- |
| `domain/models.py` | **implementado** · 8 campos requeridos, `extra="forbid"`, `SCHEMA_VERSION="v1.1"` |
| `domain/rules/base.py` | **implementado** · `Rule`, `Finding`, `Severity`, `RuleSet` |
| `domain/rules/counts.py` | **implementado** · `TotalMatchesBatch`, `FrequencyWithinTotal` |
| `domain/rules/citations.py` | **implementado** · `QuotesAreLiteral` |
| `domain/rules/versioning.py` | **implementado** · 3 reglas, el edge case del producto |
| `domain/rules/review.py` | **implementado** · 3 reglas de revisión humana |
| `domain/rules/registry.py` | **implementado** · `rule_set("baseline"\|"after")` |
| `domain/validation.py` | **implementado** · `Validator` y `RepairPolicy`, separados |
| `application/analyze_batch.py` | **implementado** · 5 pasos explícitos, con `Trace` |
| `application/types.py` | **implementado** · `AnalysisResult` |
| `ports/llm.py` | **implementado** · `LlmPort`, `LlmRequest/Response`, retryable vs terminal |
| `observability/trace.py` | **implementado** · `Trace`, `TraceStep` |
| `config.py` | **implementado** · `Settings`, valida el conjunto de reglas al arrancar |
| `application/prompting.py` | **implementado** · `PromptRegistry` lee `prompts/*.md` y comprueba su `sha256` |
| `adapters/` | **implementado** · `gemini`, `fake`, `retry`, `cache` y `build_llm()` |
| `observability/manifest.py` | **implementado** · `RunManifest` por corrida |
| `cli.py` | **implementado** · `quickdev analyze`, `eval`, `demo` |
| `prompts/` | `baseline` y `after` medidos · `v2` **sin medir** |

Son **9 reglas**, no las 12 que el plan preveía: siete comprobaciones del
validador original se fueron al sistema de tipos y las reglas que las
reimplementaran serían código muerto. La tabla de qué se fue y a dónde está en el
ADR-0003.

No queda ningún stub. Lo que falta no es código sino **mediciones**: `v2`, el
`response_schema` del proveedor y `evidencia_idx` están preparados y declarados
como no medidos (ver sección 8).

---

## 7. Cómo correrlo desde cero

Criterio de aceptación de Makers: *"alguien debe poder clonar, leer el README,
correr evals y entender qué mejoró sin preguntarles"*. Estos son los comandos
exactos, verificados en Windows con Python 3.14.

```bash
git clone https://github.com/david181222/QuickDev.git
cd QuickDev
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"     # macOS/Linux: .venv/bin/python
```

Sin API key ya se puede correr todo esto:

```bash
./.venv/Scripts/quickdev.exe demo                                # el lote de 14, sin red
./.venv/Scripts/python.exe -m pytest                             # 462 passed, 1 skipped
./.venv/Scripts/python.exe -m ruff check .                       # All checks passed!
./.venv/Scripts/python.exe scripts/gate_baseline.py              # 7/7 Puerta ABIERTA
./.venv/Scripts/python.exe -m evals --solo-regresiones
./.venv/Scripts/python.exe -m evals --modo after --replay evals/resultados/after/crudo.json
```

Solo hace falta la clave para corridas nuevas contra el modelo:

```bash
cp .env.example .env        # y pega la GEMINI_API_KEY
./.venv/Scripts/python.exe -m evals --modo after --n 10
```

### Comprobar que el dominio sigue puro

La regla estructural del proyecto es verificable, no un acuerdo verbal, y desde
`tests/domain/test_pureza.py` se comprueba sola en cada `pytest`: el test lee los
imports de cada módulo de `quickdev/domain/` con `ast` y exige que cada uno sea
stdlib sin efectos, `pydantic` o `quickdev.domain`.

```bash
.venv/bin/python -m pytest tests/domain/test_pureza.py
```

Antes esto era un `grep` que había que acordarse de correr:

```bash
grep -rnE "^\s*(import|from)\s+(google|pandas|requests|os|pathlib)" \
     --include="*.py" quickdev/domain/
```

Sigue sirviendo para una comprobación rápida, pero tiene dos límites que el test
no tiene. Busca **cinco nombres escritos a mano**, así que deja pasar
`import httpx`, `import socket` y —lo que importa— `from quickdev.adapters import
GeminiAdapter`, que es justo la violación que invertiría la dirección de las
dependencias. Y da falsos positivos: los docstrings del paquete mencionan "genai"
y "pandas" al explicar justamente esta regla.

---

## 8. Las decisiones y dónde está escrito el por qué

Cada decisión de arquitectura tiene su ADR en `docs/adr/`, con contexto,
decisión, consecuencias y alternativas descartadas.

| ADR | Qué decide |
| --- | --- |
| [0001](adr/0001-arquitectura-hexagonal.md) | Puertos y adaptadores: por qué, y qué patrones **no** usamos |
| [0002](adr/0002-convenciones-de-codigo-y-contrato.md) | Inglés en el código, español en el contrato; evolución aditiva del esquema |
| [0003](adr/0003-una-regla-una-clase.md) | Una regla, una clase; una versión, una composición. Y el bug de las citas |
| [0004](adr/0004-detectar-vs-reparar.md) | `Validator` y `RepairPolicy` separados, y la única divergencia con el validador viejo |
| [0005](adr/0005-evidencia-por-indice.md) | El modelo señala, el código cita y cuenta. Decidido, pendiente de medición |
| [0006](adr/0006-puerto-llm-y-adaptadores-decorados.md) | Reintento y caché como decoradores del puerto; `FakeLlm` para CI |
| [0007](adr/0007-resultados-versionados-y-manifiesto.md) | Un directorio y un manifiesto por corrida |
| [0008](adr/0008-correcciones-al-diagnostico.md) | Las inferencias del diagnóstico que estaban mal, con el antes y el después |
| [0009](adr/0009-structured-output-del-proveedor.md) | `response_schema` del proveedor en vez de pedir la forma por prompt. Pendiente de medir |
| [0010](adr/0010-notebook-como-demo-delgada.md) | El notebook como demo delgada, con su narrativa migrada |
| [0011](adr/0011-prompts-como-archivos-congelados.md) | Prompts congelados con `sha256`, payload según la versión, `v2` sin medir |

El índice con estado y autor de cada uno está en [`adr/README.md`](adr/README.md).

### La fidelidad del refactor está medida, no afirmada

`tests/domain/test_equivalencia_baseline.py` compara la implementación nueva
contra la salida de `evals/motor.py:validate_output`, congelada en
`tests/domain/equivalencia_baseline.json` mientras ese código todavía existía, sobre los 37 casos que existen en el repo
—las 7 regresiones y las 30 corridas guardadas— por las dos versiones del
conjunto de reglas. Compara la lista de mensajes, contenido y orden, y el reporte
ya reparado.

Resultado: **72 de 74** listas de mensajes idénticas, **14 de 14** veredictos
PASS/FAIL preservados, y **una** divergencia admitida y documentada en el
ADR-0004 (el validador viejo se tragaba un hallazgo porque corregía en medio de
la detección).

### Lo que deliberadamente no hacemos

Anotado para poder justificar su ausencia: sin contenedor de inyección de
dependencias, sin event bus, sin repositorios ni ORM, sin abstract factory sobre
proveedores que no tenemos. Son tres personas y un caso de uso. Un patrón que no
resuelve un problema que ya sentimos es solo código que hay que mantener.

---

## 9. Límites conocidos

Se listan aquí porque un documento que declara sus límites es más útil —y más
defendible— que uno que promete que todo funciona.

- **Escala no probada.** El contrato habla de "cientos de comentarios por ciclo";
  el eval más grande tiene 14. A 300 comentarios en una sola llamada, el campo
  `problemas_detectados` se degradará y `max_output_tokens` empezará a truncar.
  Falta un eval de lote grande y una estrategia de map-reduce con fusión
  determinista.
- **n = 3 es una muestra pequeña.** Con tres corridas no se distingue un fallo
  intermitente de un defecto, y la pregunta más costosa del diagnóstico
  ("¿elegimos mal el modelo?") se estaba respondiendo sobre esa base. El default
  ya está subido a 10 en `Settings`; falta correrlo.
- **Dos de las siete preguntas de diagnóstico no son independientes.** "¿Faltó
  contexto?" se deriva de un subconjunto de lo que responde "¿Falló el prompt?",
  así que nunca puede dar SÍ si la otra dio NO.
- **`contract_frozen.json` contradice al código** en dos puntos: las fuentes
  permitidas que declara no coinciden con el enum que se valida, y lista en
  `ai_job` "extraer la versión mencionada en los comentarios", que es justo el
  trabajo que el arreglo del edge case le quitó al modelo.
- **No se mide el coste.** Se registra la latencia, pero no los tokens ni el
  dinero. Sin coste, "¿elegimos mal el modelo?" no se puede responder bien: un
  modelo mejor que cuesta diez veces más puede ser la respuesta incorrecta.
- **Tres hipótesis preparadas y sin medir**: el prompt `v2` (ADR-0011), el
  `response_schema` del proveedor (ADR-0009) y `evidencia_idx` (ADR-0005). Las tres
  esperan una `GEMINI_API_KEY` válida.
- **Esto no es un agente, y hoy no debe serlo.** Es una llamada única con esquema
  fijo y validación posterior. El `Trace` de `observability/` es la costura
  preparada para que, cuando los pasos los decida un bucle en vez de una lista,
  el dominio no cambie.

# ADR-0008 · Correcciones a las inferencias del diagnóstico

- **Estado:** aceptada
- **Fecha:** 2026-09-14
- **Decide:** Miguel Moreno (`core/miguel`)
- **Afecta a:** `evals/diagnosis.py`, `evals/cases.py`, y a las respuestas de `diagnostico.md`

## Contexto

El harness deriva siete preguntas de diagnóstico del comportamiento observado, en
vez de escribirlas de memoria. Esa idea es buena y se conserva entera. Lo que
estaba mal era **cómo** se derivaban cinco de ellas.

Este ADR es el que cambia números que ya estaban commiteados, así que va con el
antes y el después de cada uno.

## Decisión

Cinco correcciones de inferencia, una ampliación del vocabulario de respuesta, y
una admisión.

---

### 1. Reintentar no es fallar

```python
# evals/motor.py:374
meta["tool_ok"] = meta["errores_json"] == 0 and meta["errores_api"] == 0
# ...y en el diagnóstico, motor.py:505
tool_mal = [f for f in filas
            if not f.get("tool_ok") or f.get("intentos", 1) > 1 or f.get("truncado")]
```

`intentos > 1` contaba como fallo de la tool. Por eso el diagnóstico del baseline
dice, sobre un eval que salió **3/3**:

> ¿La tool devolvió mal? **SÍ** — la capa de llamada falló o reintentó en 1/3 corridas

Fue un rate limit transitorio: el segundo intento salió perfecto. La tool no
devolvió mal; devolvió bien, un poco más tarde.

Ahora la tool falla si **murió o se truncó**, y los reintentos se informan aparte,
como el dato de coste que son. El `attempts` de `LlmResponse` está separado de
cualquier noción de fallo desde el puerto (ADR-0006).

### 2. El umbral de inestabilidad, explícito

```python
# evals/motor.py:500
inconsistentes = {k: v for k, v in detalle.items() if 0 < nfail(v) < n}
```

Con `n = 3`, **un solo fallo de tres corridas** bastaba para responder que el
modelo era inestable. Uno de tres no distingue un flake de un defecto, y esta es
la pregunta más cara del diagnóstico: de ella depende si se cambia de modelo.

`0 < x < n` no es un umbral, es la ausencia de uno. Ahora hay un umbral con
nombre, valores por defecto y opción de CLI:

```python
@dataclass(frozen=True)
class Umbrales:
    min_corridas: int = 5        # por debajo, la pregunta no se responde
    fraccion_minima: float = 0.2 # cuánto debe desviarse para contar como señal
```

Con n=10, un fallo (0.1) es ruido y dos (0.2) son señal. Y con n por debajo de
`min_corridas` la respuesta es **SIN DATO**, no un NO inventado. Subir n es ahora
barato gracias a la caché (ADR-0006), así que el default de `Settings.eval_runs`
es 10.

### 3. Tres estados para una aserción, no dos

```python
# evals/motor.py:409-410
except Exception:
    res[a.nombre] = False
```

Una aserción con un bug —un `KeyError` en el lambda— era **indistinguible** de una
aserción que detecta un fallo real del modelo. Lo primero es culpa nuestra y lo
segundo es un hallazgo; mezclarlos corrompe el diagnóstico entero, porque una
aserción rota se cuenta como evidencia contra el prompt.

Ahora `Resultado` es `PASA | FALLA | ERROR`. Los ERROR se cuentan aparte, salen
destacados en `diagnostico.md`, no alimentan ninguna de las siete preguntas, y
hacen que `python -m evals` termine con código 1.

### 4. En replay, n no se encoge en silencio

```python
# evals/motor.py:429-431
reg = crudos_previos.get(f"{case.id}_run{i}")
if reg is None:
    continue
```

Y más abajo, `n = len(filas)`. Si faltaba una corrida, desaparecía y el
denominador se ajustaba solo. Una tasa de «2/2» y una de «2/3» se leen igual de
bien en un informe y no significan lo mismo: la primera puede ser una corrida a la
que le faltó un dato.

Ahora `FakeLlm` lanza `SinRespuestaGrabada` si se le pide una corrida que no
tiene, el runner comprueba antes de empezar que el archivo alcanza para el n
pedido, y el diagnóstico lleva `corridas_esperadas` y `corridas_completas`
explícitos. Si no cuadran, el `diagnostico.md` lo dice en un aviso.

### 5. La admisión: dos de las siete preguntas no son independientes

```python
# evals/motor.py:512
p_ctx = por_causa(consistentes, "prompt") + por_causa(consistentes, "hitl")
# frente a, en :508
p_prompt = por_causa(fallos_crudo, "prompt")
```

`consistentes` es un **subconjunto estricto** de `fallos_crudo`: las aserciones que
fallaron en *todas* las corridas frente a las que fallaron en *alguna*. Por
construcción, «¿Faltó contexto?» no puede dar SÍ si «¿Falló el prompt?» dio NO.

No son dos señales. Son una señal y un refinamiento de esa señal. Presentarlas
como dos infla la sensación de evidencia de quien lee la tabla.

La pregunta **se conserva**, porque lo que distingue es útil: que algo falle
siempre, y no a veces, indica que la instrucción falta o es ambigua en vez de que
haya varianza. Pero se declara derivada, lleva el campo `derivada_de` en el JSON
y sale marcada en el Markdown:

> ¿Faltó contexto? **NO** — no hay fallos consistentes en todas las corridas
> *(derivada de «¿Falló el prompt?», no es una señal independiente)*

Un diagnóstico que declara sus límites es más defendible que uno que los oculta.
Esta es la corrección que menos código cambia y la que más honesto hace el
entregable.

### 6. Vocabulario: SÍ, NO y SIN DATO

Las respuestas eran binarias, así que «no lo sabemos» tenía que disfrazarse de
NO. Ahora existe `Respuesta.SIN_DATO`, y es la diferencia entre «medimos y no
pasa» y «no teníamos con qué medirlo».

---

## Consecuencias: qué cambia en el `diagnostico.md` del baseline

Aquí está la parte que hay que revisar con cuidado, porque el ADR-0003 y la
sección 7 del plan piden que el refactor **no cambie el comportamiento medido**.

**No cambió.** La reproducción está en
`evals/resultados/2026-09-14-baseline-baseline/`, generada con:

```bash
python -m evals --modo baseline --replay evals/resultados/baseline/crudo.json
```

Es idéntica a la commiteada en todo lo **observado**:

- las cinco tasas: 3/3, 3/3, 3/3, 3/3, **0/3** — iguales;
- **cada aserción fallida**, con sus fallos en crudo y tras validar — iguales,
  fila por fila;
- las 7 regresiones deterministas: 5 PASS y los 2 FAIL deliberados — iguales.

Eso está fijado como test en `tests/evals/test_replay_baseline.py`, que lee el
`diagnostico.md` commiteado y lo compara. No es una comprobación que alguien
recuerda hacer: sale roja en el siguiente `pytest`.

Lo que sí cambia son tres respuestas **derivadas** de ese comportamiento
idéntico, que son exactamente las tres inferencias corregidas:

| Eval | Pregunta | Antes | Ahora |
|---|---|---|---|
| happy_path | ¿La tool devolvió mal? | **SÍ** · «falló o reintentó en 1/3» | **NO** · «JSON válido y completo en 3/3. Hubo 1 reintento, que no cuenta como fallo» |
| input_ambiguo | ¿La tool devolvió mal? | **SÍ** · 1/3 | **NO** · 1 reintento |
| input_adversarial | ¿La tool devolvió mal? | **SÍ** · 2/3 | **NO** · 4 reintentos |
| los cinco | ¿Elegimos mal el modelo? | **SÍ** o **NO** según `0 < fallos < 3` | **SIN DATO** · 3 corridas no bastan (hacen falta 5) |
| los cinco | ¿Faltó contexto? | **NO** | **NO** *(marcada como derivada)* |

Las tres son mejoras deliberadas, no regresiones. Para verlo en una frase: **el
baseline nunca tuvo un fallo de la tool**, y el diagnóstico decía que sí en tres
de cinco evals.

Una consecuencia incómoda y honesta: hasta que se vuelva a medir con n≥5, la
pregunta «¿elegimos mal el modelo?» no tiene respuesta en ninguna de las dos
mediciones commiteadas. Antes tenía una respuesta que no estaba justificada.
Preferimos el hueco declarado.

## Alternativas descartadas

**Dejar el diagnóstico como estaba para no mover los archivos commiteados.**
Tentador, porque conserva la comparabilidad literal. Se descarta porque el
entregable del proyecto es el diagnóstico: mantener a sabiendas tres respuestas
mal derivadas para que el diff salga limpio es justo lo contrario de lo que este
repo dice hacer.

**Regenerar `baseline/diagnostico.md` con las respuestas corregidas.** Se descarta:
`baseline/` es el registro de lo que se midió y se concluyó aquel día, incluidas
sus conclusiones equivocadas. Corregirlo a posteriori borra la evidencia de la
mejora. La reproducción va en su propio directorio y este ADR explica el delta.

**Quitar «¿Faltó contexto?» por no ser independiente.** Se descarta porque la
distinción que hace —fallo consistente frente a fallo intermitente— sí aporta.
Lo que sobraba era presentarla como una segunda señal, no la pregunta.

**Un umbral estadístico de verdad** (intervalo de confianza sobre la tasa de
fallo). Es lo correcto a medio plazo y es la dirección en la que apunta
`Umbrales`. Se descarta ahora porque con n=10 el intervalo es tan ancho que la
decisión acaba siendo la misma que con una fracción fija, y una fórmula que nadie
del equipo puede defender en la sustentación es peor que un umbral explícito de
0.2 que sí se puede discutir.

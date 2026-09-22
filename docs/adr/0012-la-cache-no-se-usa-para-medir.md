# ADR-0012 · La caché no se usa para medir

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-19
- **Decide:** equipo (`prep/sustentacion`)
- **Afecta a:** `evals/runner.py` (`construir_corrida`), `tests/evals/test_cache_en_mediciones.py`,
  y tres textos que repetían la afirmación falsa: el docstring de `quickdev/adapters/cache.py`, un
  comentario de `quickdev/config.py` y el mensaje de `evals/diagnosis.py` para n < 5. Corrige una
  consecuencia que afirmaba el
  [ADR-0006](0006-puerto-llm-y-adaptadores-decorados.md).

## Contexto

`build_llm()` compone `CachingLlm(RetryingLlm(GeminiAdapter()))`, con la caché encendida por
defecto (`Settings.cache_enabled = True`). La clave de la caché (`CachingLlm.key`) es el sha256 de
modelo, prompt de sistema, payload, temperatura, `max_output_tokens` y esquema. **No incluye el
número de corrida**, y no puede: el `LlmRequest` no lo lleva.

`correr_eval` (`evals/runner.py`) ejecuta el **mismo** lote n veces con el mismo `AnalyzeBatch`, así
que las n peticiones son idénticas byte a byte. Y las corridas en vivo de evals construían el LLM
con `build_llm(settings)`, es decir, con la caché encendida. El resultado:

| n pedido | Llamadas reales al modelo | Lo demás |
| --- | --- | --- |
| 3 | 1 | 2 servidas desde `.cache/` |
| 10 | 1 | 9 servidas desde `.cache/` |
| 3, segunda medición del mismo prompt otro día | **0** | las 3 servidas desde `.cache/` |

La última fila es la peor: como la caché sobrevive al proceso, una segunda medición completa no
habría llamado al modelo ni una vez, y su `diagnostico.md` se habría leído como una medición nueva.
El manifiesto sí lo habría delatado (`desde_cache`), pero la tabla de tasas no.

### Por qué importa

Con una sola muestra real, cada aserción falla en 0/n o en n/n. Eso rompe dos de las siete
preguntas del diagnóstico:

- **"¿Elegimos mal el modelo?"** mira si una aserción pasa en unas corridas y falla en otras. Con
  una muestra repetida n veces eso no puede ocurrir: con n ≥ 5, que es cuando la pregunta se
  responde, saldría siempre **NO**, "estable".
- **"¿Faltó contexto?"** responde SÍ cuando algo falla en n/n corridas, "no es varianza". Con una
  muestra repetida, cualquier fallo, incluido un flake, se leería como fallo sistemático.

Y la varianza que la caché borraría existe: el baseline midió `hitl_marcado` fallando en crudo en
1/3, 2/3 y 1/3 corridas (happy path, input incompleto, edge case) **con `temperature = 0`**
([`baseline/diagnostico.md`](../../evals/resultados/baseline/diagnostico.md)). La medición habría
parecido estable siendo una sola muestra.

El docstring de `cache.py` decía que la caché "hace asequible subir n", y lo repetían el ADR-0006
("La caché hace asequible subir n de 3 a 10"), un comentario de `config.py` ("subir n es casi
gratis") y el propio diagnóstico, que con n < 5 respondía "Sube n: con caché es barato". Era falso:
la caché no abarata subir n, lo anula.

### La prueba

`tests/evals/test_cache_en_mediciones.py` pone un `LlmPort` que cuenta llamadas en el sitio de
`GeminiAdapter`, **dentro** de la composición real de `build_llm` y con la caché encendida en un
directorio temporal. Corre un caso en vivo con n = 3 y exige 3 llamadas al modelo.

Contra el código anterior a este ADR, falla:

```text
>       assert modelo.llamadas == 3
E       assert 1 == 3
```

Con el arreglo, pasa. Un segundo test exige 6 llamadas para dos mediciones seguidas (la fila de "0
llamadas" de la tabla), y un tercero comprueba que `build_llm` sigue cacheando en el camino del
producto.

## Decisión

**Las corridas de evals en vivo no usan caché.** En la rama no-replay de `construir_corrida`, la
configuración se copia con `cache_enabled = False` antes de llamar a `build_llm`:

```python
settings = settings.model_copy(update={"cache_enabled": False})
return Corrida(..., settings=settings, llm=build_llm(settings), ...)
```

La composición sigue siendo la de `build_llm` —mismos reintentos, mismo adaptador—; lo único que
cambia es que `CachingLlm` pasa a ser transparente. Ese interruptor ya existía y su docstring decía
para qué: "para no tener que cambiar la composición cuando se quiere medir de verdad contra la
API". Nadie lo había conectado.

**La caché se queda en el producto.** `build_llm()` no cambia y `quickdev analyze` la sigue usando:
analizar dos veces el mismo lote con la misma configuración no paga dos llamadas.

El criterio, en una frase: **la caché es para el producto; medir es muestrear, y una caché anula el
muestreo.**

El replay (`--replay`) no cambia: usa `FakeLlm` directamente y nunca pasó por `build_llm` ni por
`CachingLlm`.

## Qué datos no se vieron afectados

Ninguna medición guardada está contaminada, y conviene decir por qué en cada caso:

- **`evals/resultados/baseline/` y `after/`** se midieron el 2026-08-21 (commit `418deff`, sin
  cambios desde entonces) con el harness viejo, `evals/motor.py`, que **no tenía caché**: en ese
  archivo no aparece la palabra. Son n = 3 corridas reales por eval, 15 llamadas por medición.
- **`evals/resultados/2026-09-14-baseline-baseline/`** es un replay: `FakeLlm` sobre
  `baseline/crudo.json`, sin `build_llm` ni `CachingLlm`. Su manifiesto lo declara (`model:
  "replay"`, `desde_cache: 0`).
- En el repo **no hay ninguna medición en vivo hecha con el harness nuevo**: esas tres carpetas
  son todo lo que hay en `evals/resultados/`. El bug no llegó a producir un dato commiteado.

## Consecuencias

- Una corrida en vivo cuesta de verdad 5 × n llamadas: 15 con n = 3, 50 con n = 10. Subir n no es
  gratis, y el repo ya no lo afirma ni en `cache.py`, ni en `config.py`, ni en el texto del
  diagnóstico. El `diagnostico.md` commiteado de `2026-09-14-baseline-baseline/` conserva la frase
  vieja: es registro histórico y no se regenera.
- En el manifiesto de una corrida en vivo, `llamadas.desde_cache` tiene que ser **0**. Es la
  comprobación que hay que mirar antes de aceptar una medición.
- Las corridas de evals ya no escriben en `.cache/`.
- El párrafo del ADR-0006 sobre subir n queda corregido por este ADR. No se edita el ADR-0006: es
  el registro de lo que se decidió entonces.

## Alternativas descartadas

**Meter el número de corrida en la clave de la caché.** Obligaría a que el número de corrida
viajara en `LlmRequest` —la caché solo ve la petición—, es decir, a cambiar el dataclass del puerto
que comparten todos los adaptadores, y a que `AnalyzeBatch`, que construye la petición, supiera en
qué corrida de un eval está: un concepto del harness de medición metido en el caso de uso del
producto. Y ni siquiera arreglaría el problema: con la corrida en la clave, repetir la misma
medición otro día leería del disco las muestras de la anterior. El problema no es la clave, es usar
una caché para medir.

**Apagar la caché por defecto** (`cache_enabled = False` en `Settings`). Arregla la medición a costa
del producto, que sí se beneficia de ella. El criterio separa los dos usos; apagarla para todos no
los separa.

**Componer a mano en el runner** (`RetryingLlm(GeminiAdapter())`, sin `CachingLlm`). Funciona, pero
duplica la composición que `build_llm` existe para centralizar, y la próxima vez que cambien los
reintentos del producto la medición quedaría con otros. Con `build_llm` y `cache_enabled = False`,
producto y medición comparten todo excepto la caché.

**Documentar "borra `.cache/` antes de medir".** Depende de la disciplina de quien mide, y además no
arregla nada: dentro de una misma corrida, la corrida 1 escribe en la caché y las corridas 2..n la
leen.

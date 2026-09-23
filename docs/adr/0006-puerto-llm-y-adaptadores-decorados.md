# ADR-0006 · El puerto del modelo y sus adaptadores decorados

- **Estado:** aceptada
- **Fecha:** 2026-09-14
- **Decide:** Miguel Moreno (`core/miguel`)
- **Afecta a:** `quickdev/adapters/` (`gemini.py`, `retry.py`, `cache.py`, `fake.py`), `quickdev/ports/llm.py`

## Contexto

La llamada al modelo vivía en `evals/motor.py:213-224` y `:333-398`, y hacía
cuatro cosas en el mismo sitio: construir el cliente, llamar, reintentar y
parsear. Cuatro problemas concretos salieron de ahí, y los cuatro son medibles:

1. **Un singleton con `global _client`.** No había forma de correr dos
   configuraciones en el mismo proceso ni de sustituir el cliente en un test sin
   parchear el módulo. Estado oculto y mutable.
2. **Cualquier excepción se trataba como reintentable** (`motor.py:383-389`), con
   `time.sleep(45 * (intento + 1))`. Con una API key inválida o un 400, el eval
   se quedaba **135 segundos dormido** antes de rendirse, para un error que no
   iba a cambiar por esperar.
3. **`tool_ok = False` si hubo cualquier reintento** (`motor.py:374`), aunque el
   segundo intento saliera perfecto. Por eso el diagnóstico del baseline
   responde «¿La tool devolvió mal? **SÍ**» en un happy path que salió 3/3: fue
   un rate limit transitorio, no un fallo.
4. **El modo sin API (`--desde-crudo`) era un `if` dentro del bucle de corrida**
   (`motor.py:429-431`), no una pieza sustituible. Y ese `if` hacía `continue`
   en silencio cuando faltaba un registro.

Además, una corrida completa son 15 llamadas con n=3. Subir n —que es lo que hace
falta para responder «¿elegimos mal el modelo?» con algo más que tres muestras—
multiplicaba el coste linealmente.

## Decisión

Un puerto, `LlmPort`, con un solo método, y **cuatro implementaciones que se
componen**, porque las tres últimas implementan el mismo puerto que envuelven:

```
CachingLlm(RetryingLlm(GeminiAdapter()))   # producción
FakeLlm.from_crudo(...)                    # tests y CI
```

| Pieza | Qué sabe | Qué no sabe |
|---|---|---|
| `GeminiAdapter` | el SDK de Google, y **es el único** | que existen reintentos o caché |
| `RetryingLlm` | cuántas veces y cuánto esperar | qué proveedor hay debajo |
| `CachingLlm` | qué entradas producen qué salidas | lo mismo |
| `FakeLlm` | leer `crudo.json` | todo lo demás |

Tres decisiones dentro de esa estructura merecen justificación propia.

**La clasificación de errores vive en el adaptador, no en el decorador de
reintentos.** `GeminiAdapter` traduce `ClientError(429)` a `LlmRetryableError` y
`ClientError(400)` a `LlmTerminalError`; `RetryingLlm` solo mira de qué tipo es lo
que le llegó. Si la clasificación viviera en el decorador, cambiar de proveedor
obligaría a tocar la política de reintentos, que no tiene nada que ver con el
proveedor. Y arregla el bug de los 135 segundos: lo terminal se propaga al primer
intento, sin dormir.

**Lo desconocido es terminal, no reintentable.** Es lo contrario de lo que hacía
`motor.py`. Un error que no reconocemos tiene más probabilidad de ser un bug
nuestro que un fallo transitorio de la red, y esconderlo detrás de tres esperas
retrasa el diagnóstico sin arreglar nada.

**La caché va por fuera del reintento.** Una respuesta ya cacheada no tiene por
qué atravesar la política de reintentos: si la tienes, no hay nada que
reintentar. Al revés, además, un fallo guardado se reintentaría eternamente.

## Consecuencias

**Lo que se gana, y es el pago inmediato de toda la arquitectura:** `FakeLlm`
convierte los evals en tests de CI. El pipeline completo —prompt, llamada,
parseo, validación, reparación, aserciones, diagnóstico— corre **sin red, sin API
key, sin cuota y de forma determinista**, sobre las 30 corridas ya medidas. Eso
está en `tests/evals/test_replay_baseline.py` y se ejecuta en cada `pytest`. El
flag `--desde-crudo` deja de ser un caso especial del bucle y pasa a ser
simplemente elegir otro adaptador.

`attempts` viaja en `LlmResponse` separado de cualquier noción de fallo. Un
reintento es un dato de coste, no un defecto, y el diagnóstico ya no los confunde
(ver ADR-0008).

La caché hace asequible subir n de 3 a 10: la segunda vez que se reevalúa una
corrida ya medida, no se llama a la API. Sin eso, la corrección del umbral de
inestabilidad no sería practicable.

**Lo que cuesta:** cuatro archivos donde había un bloque de funciones, y una
composición que hay que leer de fuera hacia dentro. A cambio, cada pieza se
prueba sola: `tests/adapters/` tiene 59 tests y ninguno toca la red.

**Un filo que conviene conocer:** la caché no se invalida sola. La clave incluye
prompt, payload, modelo, temperatura y esquema, pero **no** el código del
adaptador. Si cambia cómo se parsea la respuesta, hay que borrar `.cache/` a
mano. Está anotado en el docstring de `cache.py` porque es la clase de cosa que
hace perder una tarde.

## Alternativas descartadas

**Reintentos y caché como parámetros del cliente** (`GeminiAdapter(retries=3,
cache=True)`). Es menos código, y es lo que había. Se descarta porque para probar
la política de reintentos hace falta un cliente, y para probar el cliente
arrastras la política: exactamente la mezcla que hacía intestable `motor.py`.

**Una librería de reintentos** (`tenacity`, que además ya está instalada como
dependencia transitiva del SDK). Se descarta porque lo que este proyecto necesita
no es el backoff —son quince líneas— sino la **clasificación** de errores, que es
específica del proveedor y hay que escribir igual. Añadir una dependencia directa
para ahorrar quince líneas y no resolver la parte difícil no compensa.

**Grabar y reproducir con VCR / cassettes HTTP.** Se descarta porque el repo ya
tiene su cassette: `evals/resultados/*/crudo.json`, que además es legible,
está commiteado y es el registro de una medición real. Introducir un segundo
formato de grabación sería tener dos fuentes de verdad sobre lo mismo.

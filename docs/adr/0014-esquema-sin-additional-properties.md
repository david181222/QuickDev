# ADR-0014 · El esquema que se envía a Gemini va sin `additionalProperties`

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-19
- **Decide:** equipo (`prep/sustentacion`)
- **Afecta a:** `quickdev/adapters/gemini.py`, `tests/adapters/test_gemini.py`. Corrige la
  implementación del [ADR-0009](0009-structured-output-del-proveedor.md), no su decisión.

## Contexto

La primera corrida en vivo del sistema refactorizado (`python -m evals --modo after --n 3`, sobre
`f2e1aa4`, el 2026-09-19) no llegó al modelo ni una vez. Las 15 llamadas murieron con el mismo
error terminal:

```text
400 del proveedor: Invalid JSON payload received. Unknown name "additional_properties"
at 'generation_config.response_schema': Cannot find field.
```

Manifiesto: `llamadas.total = 0`, `errores = 15`. El harness lo clasificó bien ("¿La tool devolvió
mal? SÍ"), pero la tabla de tasas decía 0/3 en cada caso. Esa corrida **no es una medición** y no se
commiteó.

**La causa es nuestra.** El ADR-0009 pasa `FeedbackReport` a `response_schema`. Los modelos del
dominio llevan `extra="forbid"`, y Pydantic lo traduce a `additionalProperties: false` en cuatro
objetos (`FeedbackReport`, `DetectedIssue`, `QuotedComment`, `DiscardedComment`). `response_schema`
acepta "a select subset of an OpenAPI 3.0 schema" (documentación del propio SDK), y ese subconjunto
no tiene ese campo. El SDK (`google-genai 2.18.1`) no lo filtra al construir la petición; lo rechaza
el servidor.

**El alcance es todo el camino en vivo**, no solo los evals: `quickdev analyze` con clave pasa por el
mismo `AnalyzeBatch` y el mismo adaptador. Desde `36acb61` (2026-09-14), el producto no podía llamar
al modelo. `quickdev demo` y los replays nunca se vieron afectados porque no llaman a la API.

**Por qué nadie lo vio:**

- El ADR-0009 se implementó sin una `GEMINI_API_KEY` válida. Lo declaraba: "implementada, pendiente
  de medir".
- `GeminiAdapter` solo se probaba con un cliente doble que no valida el esquema.
- El test del adaptador exigía `config.response_schema is FeedbackReport`: fijaba justo el bug.
- `pyproject.toml` declara un marcador `llm` para tests contra la API, pero ningún test lo usa.

## Decisión

El adaptador envía el JSON Schema del modelo **sin `additionalProperties`**, quitado de forma
recursiva (`_esquema_para_el_proveedor` en `gemini.py`). Nada más cambia:

- **El dominio conserva `extra="forbid"`.** Un campo extra en la respuesta sigue siendo un error de
  parseo en `AnalyzeBatch`, así que la garantía no se pierde: pasa de estar pedida al proveedor a
  estar solo en nuestra frontera, que es donde ya estaba comprobada.
- **El resto del esquema viaja igual.** El SDK trata un modelo Pydantic y un `dict` por el mismo
  camino (`model_json_schema()` y después `process_schema`). Comprobado sin red: el `Schema` que
  construye el SDK con el arreglo es idéntico al de antes salvo por los cuatro
  `additional_properties`.
- **Ni el puerto ni la caché cambian.** `LlmRequest.response_schema` sigue siendo `FeedbackReport`;
  la traducción a lo que acepta el proveedor es asunto del adaptador, que es el único que lo conoce.

Verificado con **una** llamada real antes de medir:
`quickdev analyze --batch docs/ejemplos/lote_normal.json` respondió al primer intento, con los ocho
campos, `version_juego = v0.8.2`, total 14, revisión humana marcada y cero hallazgos.

`tests/adapters/test_gemini.py` fija ahora que lo enviado no lleva `additionalProperties`, que el
resto del esquema llega intacto y que el dominio sigue prohibiendo campos extra. Con el adaptador
anterior, los dos primeros fallan.

## Consecuencias

- El camino en vivo funciona por primera vez desde el refactor. El sistema que se mide y se
  sustenta es este.
- **El modelo ahora ve `evidencia_idx`.** Es un campo opcional del esquema v1.1 que el prompt `after`
  no pide, y en la llamada de prueba el modelo lo rellenó en los cinco problemas. Ninguna regla lo
  usa todavía (ADR-0005). Es una de las cosas que separan "el sistema de hoy" de lo que se midió en
  `after/`, junto con el propio `response_schema`.
- La lección no se arregla con este cambio: un doble solo prueba lo que el doble sabe comprobar, y
  este no sabe qué rechaza Gemini. Sigue sin haber un test `llm` de una llamada que lo cubra.

## Alternativas descartadas

**Usar `response_json_schema`**, la otra vía del SDK, que sí acepta `additionalProperties`. Su lista
de propiedades soportadas no incluye `maxLength` ni `default`, que Pydantic sí genera, y no sabemos
si la API los ignora o los rechaza sin probarlo. Es un cambio mayor para ganar un campo que el
dominio ya comprueba.

**Quitar `response_schema` y volver a solo `response_mime_type`**, como se midió el 21 de agosto. Se
sabe que funciona, pero deshace el ADR-0009 por un campo de un esquema.

**Quitar `extra="forbid"` del dominio.** Debilita la comprobación de la frontera, obliga a regenerar
`tests/domain/golden_schema.json` y, sobre todo, cambia el dominio por una limitación de un
proveedor: la dependencia apuntaría hacia fuera.

**Construir a mano un `types.Schema`.** Duplica el contrato en un segundo sitio que puede divergir.

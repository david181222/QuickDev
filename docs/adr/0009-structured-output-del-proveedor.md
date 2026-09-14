# ADR-0009 · La forma la hace cumplir el proveedor, no el prompt

- **Estado:** aceptada · **implementada, pendiente de medir**
- **Fecha:** 2026-09-14
- **Decide:** Miguel Moreno (`core/miguel`)
- **Afecta a:** `quickdev/adapters/gemini.py`, `quickdev/ports/llm.py` (`LlmRequest.response_schema`)

## Contexto

La estructura de la respuesta se pedía con palabras. Las dos primeras líneas del
prompt de sistema, tanto en baseline como en after, son:

```
- Devuelve unicamente JSON valido.
- No uses markdown.
- No agregues campos fuera del esquema.
```

y más abajo va el esquema completo serializado como texto. Eso es pedirle al
modelo que se acuerde de una regla de formato mientras hace el trabajo real, que
es interpretar lenguaje. Y el código de alrededor demuestra que no siempre se
acordaba:

```python
# evals/motor.py:372
last_text = re.sub(r"^```json\s*|\s*```$", "", (response.text or "").strip())
out = json.loads(last_text)
```

Una expresión regular para quitar la valla de markdown que el prompt prohíbe
explícitamente, y un `except json.JSONDecodeError` con reintentos alrededor.

Hay un segundo coste, menos visible: cada instrucción de formato ocupa sitio en
el prompt y compite por atención con las instrucciones que sí son del dominio —
qué es `version_juego`, cuándo se marca revisión humana. El prompt `after` tiene
seis condiciones enumeradas para `requiere_revision_humana`; esas son las que
importan.

## Decisión

`LlmRequest` lleva un campo `response_schema: type[BaseModel] | None`, y
`GeminiAdapter` se lo pasa al proveedor:

```python
types.GenerateContentConfig(
    system_instruction=request.system_prompt,
    temperature=request.temperature,
    max_output_tokens=request.max_output_tokens,
    response_mime_type="application/json",
    response_schema=request.response_schema,   # el modelo Pydantic del dominio
)
```

`AnalyzeBatch` pasa `FeedbackReport`, que es el contrato del producto. La forma
deja de ser una petición y pasa a ser una restricción de la decodificación.

Las instrucciones de formato **se quedan en el prompt de momento**, y eso es
deliberado: quitarlas cambia el texto con el que se midieron `baseline/` y
`after/`, y eso es un cambio de comportamiento que hay que medir. Los prompts son
de `core/jose`; la limpieza va con el prompt nuevo y su medición.

## Consecuencias

Desaparece una clase entera de fallos, no un fallo:

| Fallo | Antes | Ahora |
|---|---|---|
| `JSONDecodeError` | reintento, hasta 3, con espera | no puede ocurrir por forma |
| valla de markdown | regex de limpieza | no puede ocurrir |
| campo extra | lo atrapaba `forma_del_contrato` *después* | el decodificador no lo produce |
| campo faltante | igual | igual |
| enum inválido (`sentimiento_general: "muy bueno"`) | lo atrapaba una aserción | no puede ocurrir |

Es la mejora de fiabilidad con mejor retorno por línea escrita que tiene el
proyecto ahora mismo: son cinco líneas en un `GenerateContentConfig`.

Y hay una consecuencia conceptual que vale la pena decir en voz alta, porque es
la tesis del producto aplicada un nivel más abajo. «El modelo interpreta
lenguaje, el código verifica hechos» tiene un tercer término implícito: **la
forma la garantiza la máquina**. Las reglas de `domain/rules/` siguen verificando
*hechos* —que el conteo cuadre, que la cita exista, que la versión sea la build
analizada—, que es lo que ningún esquema puede comprobar. Lo que desaparece es la
parte del validador que comprobaba *sintaxis*.

La limpieza de la valla de markdown **se conserva** en el adaptador, como cinturón
y tirantes. Cuesta una línea y protege ante un cambio de comportamiento del
proveedor.

**Lo que esto no arregla, y conviene no exagerarlo:** el esquema garantiza que
`total_comentarios_analizados` sea un entero ≥ 0. No garantiza que sea **14**.
Todos los hallazgos reales del baseline —el total equivocado, la versión de otro
build, la cita inventada— son fallos de *contenido* y siguen siendo trabajo de
las reglas. Structured output elimina el ruido, no el problema.

**Pendiente de medir.** Las mediciones commiteadas se hicieron con
`response_mime_type` pero **sin** `response_schema`. Esta decisión está
implementada y probada con dobles (`tests/adapters/test_gemini.py`), pero su
efecto sobre las tasas no está medido todavía: hace falta una corrida real contra
la API, que esta rama no puede hacer porque no hay `GEMINI_API_KEY` válida (ver
la sección 8 del plan: la clave está obsoleta y pendiente de rotar). Cuando la
haya, la corrida va a su propio directorio y se compara contra `after/`.

## Alternativas descartadas

**Function calling / tool use** en vez de structured output. Es el mecanismo más
general y permite varias herramientas. Se descarta porque aquí hay **una** salida
con **una** forma: una tool con un solo esquema es structured output con más
ceremonia y más superficie que puede fallar. Está anotado en `motor.py:207-210`
que este prototipo nunca usó function calling; la decisión se mantiene.

**Validar con Pydantic después de parsear, y reintentar con el error como
feedback.** Funciona y es lo que se hace en los sitios donde el proveedor no
soporta esquemas. Se descarta porque gasta una llamada extra para conseguir lo
que el decodificador puede garantizar gratis. La capa de reparación con el modelo
existe (`AnalyzeBatch._una_ronda_con_el_modelo`) y está apagada por decisión del
ADR-0004, pero es para errores de **contenido**, que es donde sí puede aportar.

**Quitar ya las instrucciones de formato del prompt.** Es la continuación natural
y probablemente mejore el resultado. Se descarta *en esta rama* porque cambiar el
prompt cambia lo que se mide, los prompts son de `core/jose` y un cambio de
comportamiento sin medición es exactamente lo que este proyecto dice no hacer.

# ADR-0007 · Resultados versionados y manifiesto por corrida

- **Estado:** aceptada
- **Fecha:** 2026-09-14
- **Decide:** Miguel Moreno (`core/miguel`)
- **Afecta a:** `evals/reporting.py`, `quickdev/observability/manifest.py`, `evals/resultados/`

## Contexto

Había un bug de trazabilidad en el harness, y no es un problema de estilo.

```python
# evals/motor.py:566
def carpeta(modo: str) -> Path:
    """Todo lo generado vive en evals/resultados/<modo>/."""
    d = DIR / "resultados" / modo
    d.mkdir(parents=True, exist_ok=True)
    return d
```

`escribir_salidas` hacía `df.to_csv(carpeta(modo) / "resultados.csv")` encima.
Es decir: **volver a correr los evals borraba la medición anterior**. En un
proyecto cuyo objetivo declarado es la trazabilidad, eso significa que el
registro histórico dependía de que nadie ejecutara dos veces el mismo comando.

El segundo problema es más silencioso. Los archivos de `evals/resultados/baseline/`
y `evals/resultados/after/` contienen números —12/15 y 15/15— y **ninguno dice
qué los produjo**. No hay en esos archivos nada que indique con qué prompt, con
qué conjunto de reglas, con qué modelo ni sobre qué commit se midieron. Compararlos
es, literalmente, un acto de fe: hay que creerse que el `after` se midió con lo
que alguien recuerda que se midió.

Eso importa más de lo que parece, porque la tesis del producto —«el modelo
interpreta lenguaje, el código verifica hechos»— se sostiene precisamente sobre
la comparación entre esas dos carpetas.

## Decisión

**Una corrida, un directorio nuevo.** El nombre lo compone
`evals/reporting.py:directorio_de_corrida`:

```
evals/resultados/<fecha>-<prompt_version>-<rules_version>/
```

Las tres partes son las que hacen comparable una medición y las tres van en el
nombre, para que el directorio se pueda leer sin abrir nada. Si ese nombre ya
existe —dos corridas el mismo día con las mismas versiones— se añade un sufijo
numérico: `-2`, `-3`. Ese sufijo no es cosmética: sin él, el bug de
sobrescritura volvería a entrar por la puerta de ejecutar dos veces hoy.

**`baseline/` y `after/` no se tocan.** Conservan su nombre sin fecha porque son
el registro histórico y hay código y documentos que los referencian. Además
`escribir_salidas` **lanza una excepción** si el destino se llama `baseline` o
`after`: la protección es explícita y está en `tests/evals/test_reporting.py`, no
confiada a la disciplina de nadie.

**Cada corrida escribe su manifiesto.** `quickdev/observability/manifest.py`
produce un `manifiesto.json` junto a los resultados, y su cabecera se repite
dentro del propio `diagnostico.md`, que es el archivo que la gente abre:

| Campo | Por qué está |
|---|---|
| `run_id`, `started_at`, `finished_at` | identifica la corrida |
| `prompt_version`, `rules_version`, `schema_version`, `model` | las cuatro versiones sin las cuales dos mediciones no se comparan |
| `git_sha` | sobre qué código se midió |
| `corridas` | el n, explícito, para que «12/15» no se lea sin saber de cuántas |
| `llamadas`, `desde_cache`, `intentos_totales`, `errores` | qué costó |
| `latencia`, `tokens` | agregados de coste |

Dos detalles del manifiesto que son decisiones, no implementación:

**El `git_sha` lleva el sufijo `-sucio`** cuando el árbol tiene cambios sin
commitear. Una medición tomada sobre código que no está en ningún commit **no se
puede reproducir**, y el archivo tiene que decirlo en vez de aparentar que sí.

**Las llamadas servidas por caché no entran en las latencias.** Se cuentan
aparte. Mezclarlas haría que subir el número de corridas pareciera acelerar el
modelo, que es justo la conclusión falsa que este archivo existe para impedir.

## Consecuencias

Correr los evals deja de ser destructivo. Se pueden hacer cinco corridas
comparando prompts y las cinco quedan, cada una con su estampado.

Un `diagnostico.md` suelto ya se puede auditar: dice qué prompt, qué reglas, qué
modelo, qué commit y cuántas corridas. Antes había que preguntarle a quien lo
generó.

`evals/resultados/` va a crecer. Es el coste aceptado: son archivos de texto de
unos pocos KB y son el registro de una medición, que es exactamente lo que este
proyecto dice que hay que versionar. Lo derivable —`.cache/`— se ignora.

En este PR queda una corrida de ejemplo, `2026-09-14-baseline-baseline/`, que es
la reproducción del baseline con el código nuevo y es la evidencia del ADR-0008.

## Alternativas descartadas

**Un timestamp completo en el nombre** (`2026-09-14T13-22-05-baseline-baseline`).
Ordena perfecto y nunca colisiona, pero el nombre deja de ser legible de un
vistazo y la fecha-hora rara vez es lo que se busca: se busca «la corrida del
prompt after con las reglas baseline». El sufijo `-2` resuelve la colisión sin
pagar ese precio.

**Guardar solo la última corrida y dejar el histórico a git.** Es tentador: git ya
versiona. Se descarta porque obliga a hacer `git log` y checkout para comparar
dos mediciones, cuando la operación que de verdad se hace a diario es abrir dos
archivos a la vez.

**Una base de datos de corridas (SQLite).** Consultable y ordenada. Se descarta
por la misma razón que el ADR-0001 descarta el contenedor de inyección de
dependencias: somos tres personas y los artefactos tienen que poder leerse en un
diff de GitHub durante una revisión. Un `.md` y un `.json` se revisan; una fila
de SQLite, no.

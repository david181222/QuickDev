# ADR-0002 · Convenciones de código y evolución del contrato

- **Estado:** aceptada
- **Fecha:** 2026-09-14
- **Decide:** equipo Solid
- **Afecta a:** `quickdev/domain/models.py`, y a cualquier cambio del esquema de salida

## Contexto

El código heredado mezclaba dos idiomas sin criterio: `validate_output`,
`build_input`, `run_prototype` y `OUTPUT_SCHEMA` en inglés; `fallos`,
`comentarios`, `correr_eval`, `carpeta`, `diagnosticar` y `VALORES_PERMITIDOS`
en español. Al escribir un paquete nuevo desde cero hacía falta una regla, y la
regla no es obvia porque los dos idiomas están ahí por razones distintas.

Y hay una restricción más fuerte que el estilo: **los campos del JSON de salida
son el contrato del producto**, y ya hay mediciones hechas contra ellos.
`evals/resultados/baseline/` y `evals/resultados/after/` contienen corridas
reales (12/15 y 15/15) cuyos outputs guardados usan esos nombres exactos.
Renombrar un campo no es un refactor: invalida la línea base contra la que
medimos si mejoramos.

## Decisión

### 1. Identificadores en inglés, campos del contrato en español

- **Clases, funciones, variables y alias de tipo: inglés.** `FeedbackReport`,
  `PlaytestBatch`, `Validator`, `RuleSet`, `rule_set(version)`.
- **Campos de `FeedbackReport` y de sus hijos: español, y no se renombran.**
  `resumen_general`, `sentimiento_general`, `version_juego`,
  `total_comentarios_analizados`, `requiere_revision_humana`,
  `problemas_detectados`, `comentarios_evidencia`, `comentarios_descartados`.
- **Docstrings y comentarios: español**, porque el equipo y el jurado de la
  sustentación leen en español, y la documentación es un entregable.

Los vocabularios cerrados también se quedan en español (`discord`, `bugs`,
`alta`, `extremista`): son valores del contrato, no identificadores.

### 2. El contrato evoluciona de forma aditiva

Los ocho campos existentes conservan **nombre y semántica**. Se puede:

- agregar un campo nuevo, siempre opcional y con default;
- corregir la *descripción* de un campo;
- endurecer una validación, documentándolo.

No se puede, sin una decisión explícita registrada en un ADR nuevo: renombrar,
eliminar, o cambiar el tipo de un campo existente.

### 3. Versionado del esquema

`SCHEMA_VERSION` vive en `quickdev/domain/models.py` y se estampa en cada corrida.

- `v1` — el esquema congelado original, el de las mediciones commiteadas.
- `v1.1` — idéntico más `evidencia_idx`. El bump es *menor* porque el cambio es
  aditivo: un consumidor de `v1` lee un reporte `v1.1` sin enterarse.

### 4. Los ocho campos son requeridos

Ninguno tiene default. `version_juego` es requerido-pero-nulable: el modelo tiene
que pronunciarse, aunque sea con `null`.

Esto reproduce en la frontera de parseo la comprobación original
`set(output.keys()) == REQUIRED_FIELDS`. La alternativa —darles defaults— tenía
una consecuencia inaceptable: si `comentarios_descartados` pudiera omitirse y
volverse `[]`, un lote donde el modelo descartó comentarios se vería idéntico a
uno donde no descartó ninguno, y *"nada desaparece en silencio"* dejaría de ser
cierto. La promesa de auditabilidad del producto depende de este detalle.

Por la misma razón `FeedbackReport` usa `extra="forbid"`: un campo no declarado
es un error de parseo en la frontera, no un hallazgo de validación más adentro.

## Consecuencias

Un archivo como `models.py` tiene clases en inglés con campos en español. Se ve
raro la primera vez y es correcto: el idioma marca de qué lado de la frontera
está cada cosa. `FeedbackReport` es nuestro código; `requiere_revision_humana` es
el contrato.

`CONTRACT_FIELDS` existe como constante y `tests/domain/test_contract.py`
comprueba que coincida con los campos reales del modelo, y que los ocho sean
requeridos. Renombrar un campo pone la suite en rojo: sigue siendo posible
hacerlo, pero deja de ser posible hacerlo sin darse cuenta.

## Alternativas descartadas

**Todo en inglés, campos incluidos.** Más convencional, y habría obligado a
reescribir los cinco evals, las siete regresiones y los `crudo.json` guardados,
perdiendo la comparabilidad con las dos mediciones que ya tenemos. El coste es
inmediato y el beneficio es estético.

**Todo en español.** Consistente con `motor.py` y más fácil de sustentar en
clase, pero deja el código fuera de la convención de cualquier librería con la
que interopera (`model_validate`, `BaseModel`, `Protocol`), produciendo mezclas
peores que la que evita.

**No versionar el esquema.** Era el estado anterior, y es por lo que hoy no se
puede saber con certeza qué forma produjo cada carpeta de `resultados/` sin leer
el código de ese commit.

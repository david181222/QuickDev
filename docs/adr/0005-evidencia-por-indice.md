# ADR-0005 · Evidencia por índice: el modelo señala, el código cita y cuenta

- **Estado:** aceptada · **el campo existe, la regla que lo usa no** (requiere medición)
- **Fecha:** 2026-09-14
- **Decide:** Edwin Vélez (`core/edwin`)
- **Afecta a:** `quickdev/domain/models.py` (`DetectedIssue.evidencia_idx`), y a una futura versión del conjunto de reglas

## Contexto

Hoy el modelo **escribe** las citas y **propone** las frecuencias, y el código
revisa después. Esa revisión tiene un hueco que conviene ver con precisión.

`FrequencyWithinTotal` comprueba la **cota**: ninguna frecuencia puede superar el
total del lote. Lo que no comprueba —lo que no *puede* comprobar— es el **valor**.
En un lote de 14 comentarios, una frecuencia de 3 pasa la validación aunque
ningún comentario mencione ese problema. Y una frecuencia inventada es peor que
no tener métrica: se ve creíble dentro del reporte y nadie la vuelve a contar a
mano.

Lo mismo con las citas. `QuotesAreLiteral` comprueba que el texto citado exista
en algún comentario del lote. No comprueba que ese comentario tenga algo que ver
con el problema al que se le adjunta como evidencia.

O sea: dos de las promesas centrales del producto —"no inventa conteos", "las
citas son verificables"— están sostenidas por validación *a posteriori*, que es
más débil que hacerlas imposibles.

## Decisión

Invertir quién hace qué con la evidencia.

**El modelo señala, no cita.** Para cada problema detectado devuelve
`evidencia_idx`: los índices de los comentarios del lote que lo sustentan.

**El código cita y cuenta.** A partir de esos índices:

```python
frecuencia = len(set(problema.evidencia_idx))
citas = [batch.texto_de(i) for i in problema.evidencia_idx]
```

Con eso, **las citas alucinadas y los conteos inventados dejan de ser posibles
por construcción**, en vez de ser atrapados por validación. Un índice fuera de
rango es un error de parseo, no un reporte plausible; y la frecuencia ya no es un
número que alguien propone, es el tamaño de un conjunto.

Es también la mejor frase disponible para defender el diseño: *el modelo no cita,
señala; citar es trabajo del código*.

## Qué está hecho y qué no

**Hecho.** El campo existe: `DetectedIssue.evidencia_idx: list[int]`, con default
`[]`. Es aditivo y opcional a propósito, y por eso `SCHEMA_VERSION` subió a
`v1.1` en vez de `v2`: un consumidor de `v1` lee un reporte `v1.1` sin enterarse,
y las mediciones de `baseline` y `after` siguen siendo comparables (ADR-0002).
Está cubierto por `test_evidencia_idx_es_aditivo_y_opcional`.

**No hecho, y a propósito.** No existe la regla que lo usa, ni está en ninguna
versión del conjunto de reglas. Tres razones:

1. **Cambia lo que se le pide al modelo**, así que necesita una versión de prompt
   nueva. Un prompt nuevo es un comportamiento nuevo.
2. **Cambia cómo se derivan `frecuencia` y las citas**, así que necesita una
   versión de reglas nueva, `v3`.
3. **No se puede saber si mejora sin medirlo.** Y la regla de la casa es una
   hipótesis, un cambio, una medición. Implementarlo ahora, junto con el
   refactor, haría imposible atribuir un cambio de tasa a una cosa o a la otra.

Escribirlo aquí y no implementarlo es deliberado: la decisión de diseño está
tomada y argumentada, y la implementación está enganchada a su medición.

## Cómo se implementa cuando toque

1. Prompt `v3`: pedir `evidencia_idx` y **prohibir** escribir `frecuencia` y
   `comentarios_evidencia` a mano.
2. Reglas `v3`: `EvidenceIndicesAreInRange` (cada índice `0 <= i < batch.total`)
   y `FrequencyMatchesEvidence` (`frecuencia == len(set(evidencia_idx))`).
   `FrequencyWithinTotal` deja de hacer falta: la nueva regla es más fuerte.
3. Derivar `comentarios_evidencia` en `RepairPolicy` desde los índices, en vez de
   validar el texto que vino.
4. Correr los 5 evals con `prompt=v3, rules=v3`, `n >= 10`, y comparar contra
   `after`. La hipótesis que se prueba: **los índices son una tarea más fácil para
   el modelo que copiar texto literalmente y contar.**
5. Si la tasa no mejora, se documenta y se descarta. Ese también es un resultado
   presentable.

## Consecuencias

`FrequencyWithinTotal` queda documentada con su límite explícito en el propio
docstring de la clase, apuntando aquí. Un límite escrito donde vive el código es
más útil que uno que solo está en un documento.

El campo opcional introduce un estado intermedio incómodo mientras no haya regla:
un reporte `v1.1` puede traer `evidencia_idx` y nadie lo mira. Es el precio de la
evolución aditiva, y es preferible a un `v2` incompatible que reinicie la línea
base.

## Alternativas descartadas

**Implementarlo ahora, con el refactor.** Mezcla dos cambios en una medición y
hace imposible atribuir el efecto. Es el error que este proyecto ya documentó al
arreglar el edge case de versión con prompt y validación a la vez.

**Un `v2` del esquema que elimine `comentarios_evidencia`.** Más limpio en
abstracto, y rompe la comparabilidad con `baseline` y `after`, que es el único
activo medido que el proyecto tiene.

**Dejar que el modelo devuelva ambas cosas y comprobar que coincidan.** Duplica
el trabajo del modelo para después desconfiar de él. Si el código puede derivar
el dato, pedirlo es pedirle una oportunidad de equivocarse.

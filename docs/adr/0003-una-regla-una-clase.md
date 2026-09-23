# ADR-0003 · Una regla, una clase; una versión, una composición

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-14
- **Decide:** Edwin Vélez (`core/edwin`)
- **Afecta a:** `quickdev/domain/rules/`

## Contexto

`validate_output` (`evals/motor.py:91-203`) eran 110 líneas con doce
comprobaciones encadenadas y dos ramas que cambiaban el comportamiento por
dentro:

```python
if modo == "baseline":  # línea 118
    ...
if modo == "after":  # línea 183
    ...
```

Tres problemas concretos con eso:

1. **La tercera iteración es un tercer `if`** dentro de la misma función, y cada
   edición pone en riesgo el conjunto `baseline`, que es la referencia contra la
   que se mide si mejoramos.
2. **Los fallos eran `list[str]`**, así que los evals tenían que buscar
   fragmentos de texto para saber qué había fallado:
   `any("supera el total" in f for f in fallos)`. Un cambio de redacción rompía
   un test.
3. **Un solo archivo para todo** significa que las tres personas del equipo
   chocan en él.

## Decisión

Una regla es una clase con un `id` estable y un método `check(report, batch)` que
devuelve `Finding`s. Una versión del validador es una **composición** de reglas,
no una rama dentro de una función:

```python
_VERSIONES = {
    "baseline": (TotalMatchesBatch(), VersionAppearsLiterally(), VersionIsNotNull(), ...),
    "after": (TotalMatchesBatch(), VersionAppearsLiterally(), VersionIsAnalyzedBuild(), ...),
}
```

Agregar una regla es agregar un archivo. Agregar una versión es componer una
tupla. Ninguna de las dos cosas edita código existente.

**El orden dentro de la tupla importa** y reproduce el orden en que el validador
original acumulaba sus fallos. Eso es lo que permite comparar las dos
implementaciones hallazgo por hallazgo.

### Sobre herencia: no

La tentación natural es `class ValidadorAfter(ValidadorBaseline)` sobrescribiendo
métodos. Rompería el principio de sustitución: una subclase que cambia *cuándo un
output aprueba* no es sustituible por su padre — un cliente que dependa de
`ValidadorBaseline` recibiría veredictos distintos sin saberlo. Composición de
reglas, no herencia de validadores.

## Siete comprobaciones se fueron al sistema de tipos

Al trabajar sobre un `FeedbackReport` tipado en vez de un `dict`, siete de las
quince comprobaciones del validador original **son inalcanzables**: el modelo
Pydantic ya las rechaza en el parseo. Medido, no supuesto:

| Comprobación original | Quién la hace ahora |
| --- | --- |
| `total != len(lote)` | regla `TotalMatchesBatch` |
| `version_juego` no literal | regla `VersionAppearsLiterally` |
| `version_juego` null / no es la build | reglas `VersionIsNotNull`, `VersionIsAnalyzedBuild` |
| `frecuencia > total` | regla `FrequencyWithinTotal` |
| cita no literal | regla `QuotesAreLiteral` |
| descarte sin revisión humana | reglas de `review.py` |
| `sentimiento_general` inválido | **el tipo** (`Literal`) |
| `categoria` inválida | **el tipo** |
| `prioridad` inválida | **el tipo** |
| `fuente_predominante` inválida | **el tipo** |
| `frecuencia < 1` o no entera | **el tipo** (`Field(ge=1)`) |
| `descripcion > 200` | **el tipo** (`Field(max_length=200)`) |
| `motivo` de descarte inválido | **el tipo** (`Literal`) |
| campo extra | **el tipo** (`extra="forbid"`) |

Por eso **no existen `enums.py` ni `DiscardReasonIsValid`**, que el plan de
trabajo preveía: serían código muerto, y código muerto que duplica una
restricción puede divergir de ella. La comprobación se mueve a la frontera, donde
además el proveedor la puede garantizar (ADR-0009), y queda cubierta por
`tests/domain/test_contract.py`.

Quedan **9 reglas** en vez de las 12 previstas.

## El bug de las citas literales, y cómo se decidió arreglarlo

La implementación original (`evals/motor.py:164`):

```python
any(t in real or real in t for real in textos_reales)
```

El segundo término, `real in t`, acepta una cita que **envuelve** un comentario
real con texto inventado alrededor. Es exactamente lo que la regla promete
impedir: si la cita no es literal, el desarrollador no puede volver al comentario
original y el reporte deja de ser auditable.

Arreglarlo hace la regla **más estricta**, y una regla más estricta en el conjunto
`baseline` significaría que ese conjunto ya no reproduce lo medido. Así que se
midió antes de decidir: sobre las **132 citas** de los **37 casos** disponibles
—las 7 regresiones y las 30 corridas guardadas en `crudo.json`— las dos versiones
dan **el mismo resultado en el 100 % de los casos**.

Conclusión: el arreglo cierra el hueco sin alterar ninguna medición, así que va
directo a las dos versiones en vez de esperar a una nueva. `QuotesAreLiteral`
comprueba una sola dirección, con normalización de comillas y espacios —
normalizar no afloja la regla, porque la misma cita con otro formato sigue siendo
la misma cita.

El test `test_dispara_con_una_cita_que_ENVUELVE_un_comentario_real` deja el hueco
cerrado con evidencia.

## Consecuencias

Lo que era una función de 110 líneas son ahora 9 clases en 4 archivos temáticos,
más un registro. Es más ficheros para navegar: coste real y consciente.

El falso positivo del baseline —`VersionIsNotNull` marca fallo aunque el lote
legítimamente no traiga versión— **se conserva a propósito**, con un test que lo
fija (`test_FALSO_POSITIVO_conservado_cuando_el_lote_no_trae_build`). Si alguien
lo "arregla", ese test falla y avisa de que la comparación con `after` acaba de
dejar de significar algo.

La fidelidad no es una afirmación: `tests/domain/test_equivalencia_baseline.py`
compara las dos implementaciones sobre los 37 casos × 2 versiones, mensaje por
mensaje y en orden, y sobre el reporte reparado. 74 comparaciones, una única
divergencia admitida y documentada en el ADR-0004.

## Alternativas descartadas

**Dejar el flag `modo` y solo mover la función al paquete.** Barato, y no resuelve
ninguno de los tres problemas del contexto.

**Un solo `Rule` con un diccionario de configuración por versión.** Traslada el
`if` a los datos sin eliminarlo, y las reglas dejan de poder tener lógica propia.

**Arreglar el falso positivo también en `baseline`.** Tentador, y destruye la
única línea base que el proyecto tiene medida.

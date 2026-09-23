# ADR-0004 · Detectar y reparar son dos responsabilidades

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-14
- **Decide:** Edwin Vélez (`core/edwin`)
- **Afecta a:** `quickdev/domain/validation.py`

## Contexto

`validate_output` devolvía `{"output_corregido": ..., "fallos": ..., "aprueba": ...}`.
Es decir: detectaba y corregía en la misma pasada, sobrescribiendo
`total_comentarios_analizados`, poniendo `version_juego` en `None` y forzando
`requiere_revision_humana`.

Tres consecuencias de tenerlas soldadas:

1. **No se puede preguntar "qué está mal" sin que el sistema ya lo haya
   arreglado.** Para un producto cuya promesa es la auditabilidad, eso es un
   problema de diseño, no de estilo.
2. **Son dos políticas que cambian por razones distintas.** Qué se considera un
   error depende del contrato; qué se corrige automáticamente y qué se escala a
   una persona es una decisión de producto. Mezcladas, cambiar una obliga a leer
   la otra.
3. **La corrección en medio de la detección se traga hallazgos.** Esto no era
   teórico: pasaba. Ver abajo.

## Decisión

Dos clases con una responsabilidad cada una:

```python
class Validator:
    def validate(self, report, batch) -> list[Finding]:   # solo detecta

class RepairPolicy:
    def repair(self, report, batch, findings) -> FeedbackReport:   # solo corrige
```

`Validator` no modifica el reporte. `RepairPolicy` no descubre nada nuevo: actúa
sobre los hallazgos que recibe.

Y `repair` devuelve un reporte **nuevo**: no muta el que recibe. El crudo del
modelo se conserva intacto porque los evals necesitan evaluar sus aserciones
contra las dos versiones — la diferencia entre "falló en crudo y el código lo
salvó" y "falló en crudo y sigue fallando" es lo que distingue *falló el prompt*
de *faltó validación*.

### La política de reparación es una tabla, no lógica repartida

Está en el docstring de `RepairPolicy` y se lee de una sentada:

| `rule_id` | Corrección |
| --- | --- |
| `total_matches_batch` | el total pasa a ser `batch.total` |
| `version_appears_literally` | `version_juego` pasa a null |
| `version_is_analyzed_build` | `version_juego` pasa a ser `batch.build` |
| `frequency_within_total` | **nada** |
| `quotes_are_literal` | **nada** |
| `*_requires_review` | revisión humana a true |

Más una regla global: **cualquier hallazgo fuerza `requiere_revision_humana`**.

Las dos que no se corrigen no son un olvido. No se puede adivinar cuál era la
frecuencia real ni cuál era la cita que el modelo quiso poner, y fabricar ese dato
sería exactamente lo que el producto promete no hacer. Se reportan y se escala a
una persona. Hay un test que lo fija:
`test_lo_que_no_se_repara_no_se_toca`.

## La única divergencia con el validador original

Separar las dos responsabilidades produjo **una** diferencia medible, y vale la
pena mirarla porque es el argumento a favor de la separación.

El validador original, en modo `after`:

```python
if motivos & {"sesgado", "extremista"}:
    if not output.get("requiere_revision_humana"):
        fallos.append("hay comentarios sesgados o extremistas...")
    output["requiere_revision_humana"] = True  # <-- MUTA AQUÍ
...
if (output.get("comentarios_descartados") or []) and not output.get("requiere_revision_humana"):
    fallos.append("se descartaron comentarios...")  # <-- ya es True: NO dispara
```

La mutación de la línea de arriba hace que la comprobación de abajo ya no se
cumpla, y **su hallazgo se pierde**. El sistema encontró dos razones para exigir
revisión humana y reportó una.

En la implementación nueva, como `Validator` no muta nada, las dos reglas
informan. Consecuencia medida sobre los 37 casos:

- **72 de 74** listas de mensajes son idénticas, contenido y orden.
- En **2** casos aparece ese hallazgo de más.
- **14 de 14** veredictos PASS/FAIL registrados se mantienen.
- Un número cambia en los artefactos: `after`/`discarded_bias` pasa de 1 a 2
  hallazgos en `fallos_detectados`.

Es más informativo, no incorrecto: son dos hechos distintos sobre el mismo
reporte. La divergencia está codificada explícitamente en
`test_equivalencia_baseline.py` como la **única** admitida, y el test falla si
aparece cualquier otra — la excepción no es un "contiene un mensaje más", es una
igualdad exacta.

## Consecuencias

El llamador ahora hace dos pasos donde antes hacía uno. Es el coste, y compra
poder preguntar las dos cosas por separado.

`AnalysisResult.approved` es una `@property` derivada de `findings` en vez de un
campo: no puede quedar desfasada respecto de los hallazgos.

La ronda de reparación con retroalimentación al modelo queda implementada en
`AnalyzeBatch._una_ronda_con_el_modelo` y **apagada** detrás de
`Settings.repair_round_enabled`. Se enciende cuando haya una medición de `pass@1`
contra `pass@2` que lo justifique. Encenderla sin medirla sería justo lo que la
regla de la casa prohíbe: una hipótesis, un cambio, una medición.

## Alternativas descartadas

**Que cada `Finding` lleve su valor corregido.** Mantiene la corrección junto a la
regla que la detecta, y obliga a añadir un campo a `Finding`, que es un contrato
compartido del que dependen las otras dos ramas. Además necesita un centinela,
porque `None` es un valor de reparación válido para `version_juego`. La tabla en
`RepairPolicy` cumple el objetivo declarado —que la política sea explícita y
consultable— sin tocar código de nadie.

**Reproducir la mutación intercalada para lograr equivalencia perfecta.** Exigiría
que una regla sepa lo que otra encontró, que es el acoplamiento que este ADR
existe para evitar. Y conservaría un comportamiento que se trague hallazgos.

# Evals de QuickDev

Dos tipos de prueba, con propósitos distintos:

| | Regresiones | Evals del producto |
| --- | --- | --- |
| Qué prueban | que el **código** (el validador) siga cumpliendo lo que prometía | si el **modelo** se porta bien con cada tipo de lote |
| ¿Llaman al modelo? | no: deterministas, gratis e instantáneas | sí, o reproducen corridas ya grabadas |
| Dónde | [`regressions.py`](regressions.py), filas de [`quickdev_regression_cases.csv`](quickdev_regression_cases.csv) | [`cases.py`](cases.py): 5 casos con hipótesis y aserciones |
| Resultado | 7 PASS con reglas `after`; 5 PASS / 2 FAIL con `baseline` (falso positivo conservado) | tasa por caso y 7 preguntas de diagnóstico |

Por qué las regresiones no llaman al modelo: [`docs/historia/por-que-las-regresiones-no-llaman-al-modelo.md`](../docs/historia/por-que-las-regresiones-no-llaman-al-modelo.md).

## Cómo usarlos

Desde la raíz del repo, con `pip install -e ".[dev]"` hecho (en Windows, `.venv/Scripts/...`):

```bash
# Regresiones: sin API, instantáneo
.venv/bin/quickdev eval --prompt after --solo-regresiones

# Reproducir una medición guardada: sin API, sin red
.venv/bin/quickdev eval --prompt baseline --replay evals/resultados/baseline/crudo.json

# Medir de verdad: necesita GEMINI_API_KEY en .env
.venv/bin/quickdev eval --prompt after --n 10
```

`quickdev eval` es un atajo de `python -m evals` (`--prompt` es `--modo`, `--rules` es
`--rules-version`); cualquiera de los dos sirve. La versión de reglas, si no se indica, es la que
declara el prompt: `v2` se mide con `after`.

Cada corrida escribe en su propio directorio, `resultados/<fecha>-<prompt>-<reglas>/`, cinco
archivos: `resultados.csv`, `diagnostico.md`, `crudo.json`, `regresion.csv` y `manifiesto.json`.
Nunca pisa una corrida anterior ([ADR-0007](../docs/adr/0007-resultados-versionados-y-manifiesto.md)).

## Qué hay en `resultados/`

| Directorio | Qué es |
| --- | --- |
| `baseline/` | Medición histórica con el prompt y las reglas originales: **12/15** |
| `after/` | Medición histórica tras el diagnóstico: **15/15** |
| `2026-09-14-baseline-baseline/` | Replay del baseline al migrar el harness; reproduce lo medido con las respuestas de diagnóstico corregidas ([ADR-0008](../docs/adr/0008-correcciones-al-diagnostico.md)) |

`baseline/` y `after/` no se regeneran ni se editan: son la línea base.

## Un replay solo reproduce lo que se midió

`--replay` usa `FakeLlm`, que busca cada corrida por su input exacto. Por eso:

- sirve para `baseline` y `after`, que comparten la forma del input;
- **no** sirve para `v2`, que envía los comentarios como array JSON y no está medido: pedirlo falla
  antes de correr, en vez de producir un "0/15" falso;
- un eval recién agregado no tiene corridas grabadas: sale como corrida muerta hasta que se mida.

Cómo agregar un eval: [`README.md`, sección 4](../README.md#4-dos-recetas).

## Regla

El modelo interpreta lenguaje. El código verifica hechos: conteos, enums, citas literales y
condiciones de revisión humana.

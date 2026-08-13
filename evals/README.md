# Evals de regresion QuickDev

Este repo ya tiene una buena base: schema congelado, `validate_output` y pruebas adversariales. Esta carpeta deja una lista pequena de regresion para que el equipo no pierda esas garantias al seguir iterando.

## Como usarlos

1. Abre `QuickDev_01.ipynb`.
2. Ejecuta hasta definir `validate_output`, `run_prototype` y `contract_check`.
3. Crea el input de cada fila de `quickdev_regression_cases.csv`.
4. Marca `PASS` si la validacion detecta o corrige el problema esperado.

## Regla pedagogica

El modelo interpreta lenguaje. El codigo verifica hechos: conteos, enums, citas literales y condiciones de revision humana.

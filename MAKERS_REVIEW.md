# Makers Review

## Que encontramos

- Es el repo con mejor separacion entre modelo y validacion.
- Tiene `OUTPUT_SCHEMA` congelado y validacion determinista de conteos, enums y citas.
- Los tests adversariales tienen criterios PASA/FALLA.
- La tasa guardada es 4/5, lo cual es bueno pedagogicamente porque muestra una falla real.
- No habia una carpeta `evals/` versionada para convertir esas pruebas en regresion mantenible.

## Mejora aplicada

Agregue `evals/quickdev_regression_cases.csv` y `evals/README.md` para convertir las garantias del notebook en una suite de regresion explicita.

## Por que importa

Cuando un equipo mejora prompts, puede romper validaciones que antes funcionaban. Una suite de regresion protege los contratos: no inventar conteos, no citar evidencia falsa y no ocultar comentarios descartados.

## Como probarlo

1. Abre `QuickDev_01.ipynb`.
2. Ejecuta hasta `validate_output` y `run_prototype`.
3. Usa los escenarios de `evals/quickdev_regression_cases.csv`.
4. Comprueba que cada escenario active la validacion esperada.

## Tu reto

1. Core: transformar cada fila del CSV en una celda de prueba concreta.
2. Intermediate: guardar resultados en `evals/results.csv`.
3. Advanced: extraer `validate_output` a un script Python reusable y ejecutarlo sin depender del notebook.

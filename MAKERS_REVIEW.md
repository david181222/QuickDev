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

<!-- MAKERS_REVIEW_2026_08_27_START -->
## Revision docente - 2026-08-27

### Lo que vimos

- QuickDev tiene de los avances mas serios en evaluacion: baseline, after, diagnostico y regresion.
- Edwin, Jose Elias y Miguel empujaron el proyecto hacia artefactos versionados, no solo notebook.
- El motor de evals y los reportes ya parecen base de AI Engineering real.
- Falta que el flujo sea facil de correr desde cero para alguien externo.
- El riesgo ahora no es falta de trabajo; es que la evidencia quede dispersa y dificil de leer.

### Reto de hoy

Hagan el proyecto corrible y explicable:

1. En README.md, agregar comandos exactos para instalar y correr evals.
2. Crear una tabla corta: baseline, after, regresiones y fallas pendientes.
3. Dejar una siguiente hipotesis tecnica concreta.

### Tarea obligatoria: diagrama de arquitectura

Crear docs/arquitectura.md con un diagrama Mermaid que muestre:

`mermaid
flowchart LR
  EntradaProyecto --> AgenteQuickDev
  AgenteQuickDev --> ContratoSalida
  ContratoSalida --> MotorEvals
  CasosEval --> MotorEvals
  MotorEvals --> ReporteBaseline
  MotorEvals --> ReporteAfter
`

El diagrama debe mostrar que parte es notebook, que parte es motor, donde estan los casos y donde quedan resultados.

### Criterio de aceptacion

Alguien debe poder clonar, leer README, correr evals y entender que mejoro sin preguntarles.
<!-- MAKERS_REVIEW_2026_08_27_END -->


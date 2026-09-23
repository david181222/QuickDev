# Makers Review

## Que encontramos

- Es el repo con mejor separacion entre modelo y validacion.
- Tiene `OUTPUT_SCHEMA` congelado y validacion determinista de conteos, enums y citas.
- Los tests adversariales tienen criterios PASA/FALLA.
- La tasa guardada es 4/5, lo cual es bueno pedagogicamente porque muestra una falla real.
  > **Obsoleto (2026-09-14, `core/jose`).** Ese 4/5 era la tabla de pruebas adversariales de la
  > Parte 7 del notebook: cinco casos, una corrida cada uno, y fallaba el caso `normal`. Esa tabla
  > ya no existe. Las mediciones vigentes estan en `evals/resultados/`: **baseline 12/15** (edge
  > case de version 0/3) y **after 15/15**, con 3 corridas por eval. No son comparables con el
  > 4/5. Detalle en `CHANGELOG.md`.
- No habia una carpeta `evals/` versionada para convertir esas pruebas en regresion mantenible.

## Mejora aplicada

Agregue `evals/quickdev_regression_cases.csv` y `evals/README.md` para convertir las garantias del notebook en una suite de regresion explicita.

## Por que importa

Cuando un equipo mejora prompts, puede romper validaciones que antes funcionaban. Una suite de regresion protege los contratos: no inventar conteos, no citar evidencia falsa y no ocultar comentarios descartados.

## Como probarlo

> **Obsoleto (2026-09-14, `core/jose`).** Los pasos de abajo ya no funcionan: el notebook no
> define `validate_output` ni `run_prototype`, porque dejo de contener logica (ADR-0010). Se
> conservan como registro de lo que se pidio. Hoy, cada fila de
> `evals/quickdev_regression_cases.csv` es una regresion ejecutable:
>
> ```bash
> .venv/bin/python -m pytest tests/domain/test_regressions.py
> .venv/bin/quickdev eval --prompt after --solo-regresiones      # 7/7 PASS
> ```

1. Abre `QuickDev_01.ipynb`.
2. Ejecuta hasta `validate_output` y `run_prototype`.
3. Usa los escenarios de `evals/quickdev_regression_cases.csv`.
4. Comprueba que cada escenario active la validacion esperada.

## Tu reto

1. Core: transformar cada fila del CSV en una celda de prueba concreta.
2. Intermediate: guardar resultados en `evals/results.csv`.
3. Advanced: extraer `validate_output` a un script Python reusable y ejecutarlo sin depender del notebook.

> **Estado (2026-09-14).** Core: hecho, y luego llevado de celdas a `tests/domain/test_regressions.py`.
> Intermediate: hecho de otra forma, cada corrida escribe su propio `evals/resultados/<fecha>-<prompt>-<reglas>/`
> (ADR-0007). Advanced: hecho, `validate_output` es `Validator` + `RepairPolicy` en
> `quickdev/domain/validation.py`, sin notebook (ADR-0003, ADR-0004).
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


<!-- MAKERS_CODE_ARCH_REVIEW_2026_09_01_START -->
## Revision de codigo y arquitectura - 2026-09-01

### Lectura docente

- Tienen de las mejores evidencias del grupo: baseline, after, diagnostico y regresion.
- Falta arquitectura visible: no se detecto docs/arquitectura.md.
- El trabajo tecnico existe, pero todavia puede ser dificil de entender desde cero.
- Abel debe quedar visible si ya esta asociado al equipo.

### Revision de principios

- Bien: estan pensando en evaluacion y regresion, que es AI Engineering real.
- Falta: reproducibilidad para un tercero.
- Falta: documentar la frontera entre notebook, motor de evals, casos, outputs y reportes.

### Pendiente de equipo

Crear docs/arquitectura.md y dejar README con comandos exactos para correr evaluacion desde cero.

### Pendiente por poca evidencia individual

Abel debe hacer un commit propio. Si no ha entrado al flujo, asignarle un aporte pequeno: documentar arquitectura, correr evals o agregar un caso de regresion.
<!-- MAKERS_CODE_ARCH_REVIEW_2026_09_01_END -->

> **Estado (2026-09-14).** Comandos exactos: `README.md`, seccion 2. Tabla baseline / after /
> regresiones / fallas pendientes: `README.md`, secciones 5 y 6. Siguiente hipotesis tecnica:
> el prompt `v2` (comentarios como array JSON), preparado y pendiente de medir (ADR-0011).
> Diagrama: `docs/arquitectura.md`, que refleja la estructura actual (`MotorEvals` es hoy
> `evals/runner.py` + `diagnosis.py` + `reporting.py`; `CasosEval`, `evals/cases.py`).
<!-- MAKERS_REVIEW_2026_08_27_END -->

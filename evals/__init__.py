"""Suite de evals de QuickDev.

Un modulo por responsabilidad. Antes eran dos archivos, `motor.py` (690 lineas,
seis responsabilidades) y `casos.py`; trabajando de tres, cualquier cambio tocaba
el mismo archivo y todas las ramas chocaban.

- `cases.py`          los 5 evals del producto y sus aserciones. ESTE es el que
                      se edita para agregar o cambiar un eval.
- `regressions.py`    las 7 regresiones deterministas del validador. Sin modelo.
- `runner.py`         orquestacion: corre el pipeline n veces por caso.
- `diagnosis.py`      las 7 preguntas, derivadas del comportamiento observado.
- `reporting.py`      los escritores y el directorio versionado de cada corrida.

Los prompts no viven aqui: estan en `prompts/*.md` y los sirve
`quickdev.application.prompting.PromptRegistry`.

Uso desde la raiz del repo:

    .venv/Scripts/python.exe -m evals --solo-regresiones
    .venv/Scripts/python.exe -m evals --modo baseline --replay evals/resultados/baseline/crudo.json
    .venv/Scripts/python.exe -m evals --modo after --n 10

`resultados/baseline/` y `resultados/after/` son mediciones reales commiteadas.
No se regeneran ni se sobrescriben: son la linea base y el registro historico.
Cada corrida nueva escribe en su propio directorio. Ver ADR-0007.
"""

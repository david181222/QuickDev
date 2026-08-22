"""Suite de evals de QuickDev.

Dos modulos, nada mas:

- `motor`  : el esquema congelado, `validate_output`, la llamada al modelo y la
             derivacion del diagnostico. No se toca al agregar casos.
- `casos`  : los 5 evals del producto y las regresiones deterministas. Este es
             el archivo que se edita.

Uso desde la raiz del repo:

    .venv/Scripts/python.exe -m evals.motor --modo baseline --n 3
"""

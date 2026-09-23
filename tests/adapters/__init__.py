"""Tests de los adaptadores del puerto LlmPort.

Esta carpeta es un paquete -tiene `__init__.py`- y las de `core/edwin` no. No es
un descuido: es lo que evita que un `conftest.py` aqui rompa los suyos.

pytest, en modo `prepend`, mete en `sys.path` el directorio base de cada modulo
de test. Sin `__init__.py`, ese directorio es esta carpeta y el conftest de aqui
se registraria en `sys.modules` como `conftest` a secas, compitiendo con
`tests/conftest.py`; `tests/domain/test_rules.py:8` hace `from conftest import
BASURA, ...` y se llevaria el modulo equivocado. Con `__init__.py`, el directorio
base pasa a ser `tests/` y este conftest se llama `adapters.conftest`, que no
colisiona con nada.
"""

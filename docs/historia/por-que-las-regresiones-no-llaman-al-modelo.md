# Por qué las regresiones no llaman al modelo

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celda 27, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

# Parte 8b - Suite de regresion: cada fila del CSV como prueba concreta

**Reto Core del review.** `evals/quickdev_regression_cases.csv` describe cinco escenarios en
prosa: que forma tiene el input y que deberia detectar la validacion. En prosa no protegen nada.
Aqui cada fila se convierte en una celda ejecutable con criterio PASS/FAIL evaluado por codigo.

Dos decisiones de diseno que conviene poder defender:

**1. Estas pruebas no llaman al modelo.** No prueban a Gemini, prueban a `validate_output`. Cada
caso parte de un output sintetico correcto y perturba **una sola cosa**, para comprobar que la
validacion atrapa justo esa cosa y no otra. Por eso son deterministas, gratis e instantaneas:
una suite que cuesta dinero y tarda un minuto no se corre, y una suite que no se corre no protege
nada.

**2. En que se diferencian de la Parte 7.** Alli los casos adversariales miden si el *modelo* se
porta bien, y el resultado cambia entre corridas. Aqui se mide si el *codigo* sigue cumpliendo lo
que prometia. Si alguien mejora el prompt y de paso rompe una validacion que antes funcionaba,
esto lo detecta sin gastar una sola llamada.

Al leer el resumen final, mira la columna `fallos_detectados`: en cuatro de los cinco casos
aparece un fallo `version_juego es null` que no tiene nada que ver con lo que ese caso prueba.
Es ruido real del validador actual, y la suite lo deja a la vista en vez de taparlo.

---

## Dónde vive esto hoy

Las regresiones viven en `evals/regressions.py` y `tests/domain/test_regressions.py`, y `scripts/gate_baseline.py` las compara contra `evals/resultados/baseline/regresion.csv`. El ruido `version_juego es null` que describe el último párrafo es el falso positivo del conjunto de reglas `baseline`, que se conserva a propósito como registro y se corrigió en `after`.

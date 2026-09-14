# Las validaciones deterministas son el corazón de la corrección

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celda 21, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

## Parte 6b — Validaciones deterministas posteriores

Esta celda es el corazon de la correccion. Un prompt puede pedirle al modelo que no invente
numeros, pero **una instruccion no es una garantia**. Los conteos y las citas se verifican con
codigo, y si algo no cuadra el sistema fuerza `requiere_revision_humana = True`.

Esta es la frontera del contrato: el modelo interpreta lenguaje, el codigo verifica hechos.

---

## Dónde vive esto hoy

`validate_output` se partió en dos (ADR-0004): `Validator` detecta y `RepairPolicy` corrige, en `quickdev/domain/validation.py`. Cada regla es una clase en `quickdev/domain/rules/` (ADR-0003).

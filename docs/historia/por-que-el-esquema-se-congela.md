# Por qué el esquema se congela y el lote es una lista

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celda 17, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

# Parte 6 — Construir un prototipo ejecutable

Dos cambios de fondo respecto de la version anterior.

**1. El esquema se congela.** Antes, `OUTPUT_SCHEMA = contract.output_fields` significaba que el
esquema lo inventaba el modelo en cada corrida, y luego la Parte 8 verificaba el output contra ese
mismo esquema recien inventado: el sistema se calificaba a si mismo. Ahora el equipo fija el
esquema y el contrato generado se **contrasta** contra el.

**2. El lote es una lista, no una frase.** Antes el input decia "214 comentarios en total" y
listaba 8, asi que el modelo no tenia mas remedio que fabricar `total_comentarios_analizados` y
las `frecuencia`. Ahora los comentarios son una lista de Python, el texto del input lo arma el
codigo, y el total real es `len(COMENTARIOS)`. Contar deja de ser adivinar.

---

## Dónde vive esto hoy

El esquema congelado es `FeedbackReport` en `quickdev/domain/models.py`, protegido por `tests/domain/test_contract.py` y `tests/domain/golden_schema.json`. El lote es `PlaytestBatch`, y `TotalMatchesBatch` compara `total_comentarios_analizados` contra `batch.total`.

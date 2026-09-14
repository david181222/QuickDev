# Correcciones de la versión 1

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celda 0, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

### Qué se corrigió respecto de la versión anterior

| # | Problema | Corrección |
|---|---|---|
| 1 | La Parte 5 era una copia de la Parte 4; no existía el diagrama Mermaid pedido en el entregable | Parte 5 genera el diagrama con código determinista, sin llamar al modelo |
| 2 | `ask_gemini_json` estaba redefinida 3 veces con comportamientos distintos | Una sola definición, en la Parte 0 |
| 3 | El esquema de salida lo inventaba el modelo en cada corrida, así que `contract_check` se comparaba contra sí mismo | `OUTPUT_SCHEMA` congelado por el equipo; el contrato generado se contrasta contra él |
| 4 | El input decía "214 comentarios" pero listaba 8, así que el modelo fabricaba `total_comentarios_analizados` y `frecuencia` | El lote es una lista de Python; el texto del input lo arma el código y los conteos se verifican contra `len()` |
| 5 | La prueba de prompt injection no tenía criterio de aprobación | Parte 7 evalúa cada caso adversarial con PASA/FALLA automático |
| 6 | `contract_check` solo comparaba nombres de campos | Parte 8 valida además enums, rangos y que las citas existan literalmente en el input |

---

## Dónde vive esto hoy

Cada corrección de esa tabla sobrevivió a la migración al paquete `quickdev/`: el esquema congelado es `FeedbackReport` (`quickdev/domain/models.py`), los conteos se verifican en `quickdev/domain/rules/counts.py`, las citas en `quickdev/domain/rules/citations.py`, y la llamada al modelo tiene una sola implementación (`quickdev/adapters/gemini.py`).

# Helper único de llamada

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celda 3, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

### Helper único de llamada

Antes esta función estaba definida tres veces, con `max_tokens` y manejo de errores distintos
en cada copia. Eso hacía que el comportamiento dependiera de qué celda se hubiera ejecutado de
último. Ahora se define **una sola vez**.

---

## Dónde vive esto hoy

El mismo principio llevado más lejos: la composición de producción está en un solo sitio, `build_llm()` en `quickdev/adapters/__init__.py`, y el reintento y la caché son decoradores del puerto (ADR-0006).

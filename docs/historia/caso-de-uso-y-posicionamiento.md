# El caso de uso: de una idea vaga a un caso defendible

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celdas 5, 7, 9, 10, 12, 35, 37, 39, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

<!-- celda 0, encabezado -->

# MAKERS AI Product — Case Selector Lab
## QuickDev — de una idea vaga a un caso de uso AI defendible

**Equipo:** Solid · **Producto:** QuickDev · **Output:** `analisis_feedback_playtest`

Al terminar este notebook el equipo tiene:
1. Usuario específico
2. Job-to-be-done
3. Problem thesis
4. Evidencia mínima
5. Ventaja concreta de IA
6. Input -> decisión -> output
7. Riesgo principal
8. Contrato JSON congelado y verificado
9. Pitch de 60 segundos

> Regla: no se construye nada hasta demostrar que el problema merece IA.

---

<!-- celda 5 -->

# Parte 1 — Reality check

Antes de formular el producto, hay que probar que existe una fricción real.
Se llena con **hechos**, no con imaginación.

**Nota de posicionamiento.** El caso está formulado alrededor del *playtest*, es decir,
**antes del lanzamiento**. Las herramientas comerciales que ya existen (HowlRound, Steam
Sentimeter, PlayerIntel, SteamReview AI) analizan **reseñas de Steam**, que solo existen
*después* de publicar. En el playtest no hay reseñas: el feedback vive en Discord privado,
formularios y builds de itch.io. Ese es el momento que ataca QuickDev, y es lo que lo separa
de la competencia existente.

---

<!-- celda 7 -->

# Parte 2 — ¿IA o software tradicional?

La IA aporta valor cuando el trabajo exige interpretar informacion variable o no estructurada.
No aporta valor solo porque el producto suene moderno.

---

<!-- celda 9 -->

## Semaforo

- **8-10:** candidato fuerte para prototipo
- **5-7:** necesita evidencia o mejor acotacion
- **0-4:** probablemente es una idea, no un caso de uso

---

<!-- celda 10 -->

# Parte 3 — El modelo como critico, no como autor complaciente

El modelo debe intentar **matar la idea** antes de mejorarla.

---

<!-- celda 12 -->

# Parte 4 — Generar el contrato de producto

Solo si el caso obtiene `GO` o un `REFRAME` razonable.

El contrato separa tres responsabilidades que no se deben mezclar:

- **`system_validations`**: lo que verifica codigo determinista, sin el modelo.
- **`ai_job`**: lo que hace el modelo, que es interpretar texto.
- **`human_decision`**: lo que decide una persona y el sistema nunca ejecuta solo.

---

<!-- celda 35 -->

# Parte 9 — Comparar dos ideas y matar una

Cada equipo propone dos casos. Solo uno pasa.

---

<!-- celda 37 -->

# Parte 10 — Pitch de 60 segundos

Se genera el pitch, pero el equipo debe defenderlo sin leer.

---

<!-- celda 39 -->

# Entregable del equipo

Copien y entreguen:

- `evaluation` (Parte 3)
- `contract` (Parte 4)
- `mermaid_diagram` exportado como imagen desde mermaid.live (Parte 5)
- Output del caso normal (Parte 6)
- Lista de fallos que atrapo `validate_output` (Parte 6b)
- Tabla `df_tests` de pruebas adversariales con PASA/FALLA (Parte 7)
- Resultado de `contract_check` (Parte 8)
- Pitch de 60 segundos (Parte 10)
- Evidencia que recogeran en las proximas 48 horas

## Definition of Done

- [ ] Usuario especifico
- [ ] Momento concreto (playtest, antes del lanzamiento)
- [ ] Evidencia minima, incluida la competencia existente
- [ ] Alternativa actual
- [ ] Ventaja de IA demostrable
- [ ] Input disponible
- [ ] Output verificable por codigo, no solo por lectura
- [ ] Baseline sin IA
- [ ] Riesgo principal
- [ ] Revision humana definida y forzada automaticamente
- [ ] Metrica de exito
- [ ] Prototipo probado con 5 casos, cada uno con criterio de aprobacion

## Lo que hay que poder defender en la sustentacion

1. **Por que el modelo no cuenta.** `frecuencia` y `total_comentarios_analizados` son conteos;
   los produce codigo y se verifican contra `len()`. Una instruccion en el prompt no es una
   garantia; una validacion posterior si.
2. **Por que nada desaparece en silencio.** Todo comentario que el modelo descarta queda en
   `comentarios_descartados` con su motivo, asi que el desarrollador puede auditar que se ignoro.
3. **Por que el momento importa.** Las herramientas que ya existen analizan reseñas de Steam,
   que solo existen despues de publicar. QuickDev entra en el playtest, cuando el feedback
   todavia puede cambiar el diseño.

---

## Dónde vive esto hoy

El contrato que salió de la Parte 4 está congelado en `evals/contract_frozen.json`. Las Partes 1-3 y 9-10 llamaban al modelo para criticar la idea y generar el pitch; eran ejercicios de selección del caso, no parte del producto, y no se migraron a código.

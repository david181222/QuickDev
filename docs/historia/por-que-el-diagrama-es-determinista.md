# Por qué el diagrama se construye con código

> **Registro histórico.** Texto copiado sin editar de `QuickDev_01.ipynb` (celdas 14, 15, 16, `main @ a706440`), antes de que el notebook quedara como demo delgada (ADR-0010). No se reescribe para que suene mejor: es el argumento tal como se escribió. Los nombres que menciona (`validate_output`, `ask_gemini_json`, Parte N) son del notebook, no del paquete actual.

---

# Parte 5 — Visualizar el AI Flow

**Esta es la seccion que estaba rota:** antes repetia la celda de la Parte 4 y nunca generaba
el diagrama, aunque "Diagrama Mermaid" aparece en la lista de entregables.

El diagrama se construye con **codigo determinista a partir del contrato**, no pidiendoselo al
modelo. Asi el diagrama siempre corresponde exactamente a lo que dice el contrato, y no cambia
entre corridas.

### El código original (celda 15)

Bloque marcado como `text` a propósito: así `ruff format` no lo reformatea y el registro queda literal.

```text
def build_mermaid(contract) -> str:
    def clean(s, n=58):
        s = re.sub(r'["\[\]{}()|]', "", str(s)).replace("\n", " ").strip()
        return (s[:n] + "...") if len(s) > n else s

    lines = ["flowchart TD"]
    lines.append('    IN["Entrada: lote de comentarios del playtest"]')

    # Validaciones deterministas
    lines.append('    subgraph DET["Software determinista - sin IA"]')
    for i, v in enumerate(contract.system_validations[:5], start=1):
        lines.append(f'    V{i}["{clean(v)}"]')
    lines.append("    end")

    # Trabajo del modelo
    lines.append('    subgraph AI["Modelo - interpretacion de lenguaje"]')
    for i, j in enumerate(contract.ai_job[:5], start=1):
        lines.append(f'    A{i}["{clean(j)}"]')
    lines.append("    end")

    lines.append('    CHK["Post-validacion: conteos, enums y citas verificadas por codigo"]')
    lines.append('    REV{"requiere_revision_humana"}')
    lines.append(f'    HUM["{clean(contract.human_decision)}"]')
    lines.append('    OUT["analisis_feedback_playtest (JSON)"]')

    n_v = min(len(contract.system_validations), 5)
    n_a = min(len(contract.ai_job), 5)

    lines.append("    IN --> V1" if n_v else "    IN --> A1")
    for i in range(1, n_v):
        lines.append(f"    V{i} --> V{i+1}")
    if n_v and n_a:
        lines.append(f"    V{n_v} --> A1")
    for i in range(1, n_a):
        lines.append(f"    A{i} --> A{i+1}")
    if n_a:
        lines.append(f"    A{n_a} --> CHK")
    lines.append("    CHK --> REV")
    lines.append('    REV -->|true| HUM')
    lines.append('    REV -->|false| OUT')
    lines.append("    HUM --> OUT")
    return "\n".join(lines)

mermaid_diagram = build_mermaid(contract)
print(mermaid_diagram)
```

Copia el texto anterior en [Mermaid Live Editor](https://mermaid.live/) para exportar la imagen
del diagrama y mostrarla durante el pitch.

---

## Dónde vive esto hoy

`build_mermaid` no se migró al paquete. Generaba el diagrama a partir del contrato que producía el modelo (luego congelado en `evals/contract_frozen.json`), y ese archivo hoy contradice al código en dos puntos (fuentes permitidas y un `ai_job` que el modelo ya no hace). Generar el diagrama del README desde ahí publicaría esas contradicciones. El diagrama vigente se mantiene a mano en `docs/arquitectura.md` y `README.md`, contra el código real. El principio de esta celda —el diagrama no se le pide al modelo— se conserva.

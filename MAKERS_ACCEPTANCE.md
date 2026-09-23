# Gates Makers — revisión 2026-09-23

Referencia revisada: `origin/main`, integrada localmente en `makers/review`.

| Gate | Estado | Evidencia | Para cerrar |
|---|---|---|---|
| Arquitectura atribuible | PASS | ADRs, `docs/arquitectura.md` y roles de Edwin, Miguel, José y Abel. | Los cuatro deben explicar una decisión fuera de su rol. |
| Uso de IA + evals | PASS | Baseline 12/15, after 15/15, replay y resultados versionados. | Mantener gate al introducir feedback real. |
| Jailbreak y safety | PASS | Contrato congelado, evidencia por índice y reglas deterministas. | Probar el mismo contrato con input de un estudio real. |
| Mantenibilidad | PARCIAL | Arquitectura modular; cuatro módulos superan 300 líneas. | Separar UI Streamlit y responsabilidades del runner/diagnóstico. |
| Producto ejecutable | PASS | CLI + Streamlit. | Piloto con un estudio y una decisión verificable. |
| Git profesional | PASS | CI verde, contribuciones atribuibles e integración en `main`. | Mantener PRs pequeños. |

El siguiente avance válido es evidencia de usuario, no otra capa de arquitectura.

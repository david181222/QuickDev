# Historia del proyecto

El "por qué" de las primeras decisiones de QuickDev se escribió dentro de las celdas markdown de
`QuickDev_01.ipynb`. Cuando el notebook pasó a ser una demo delgada (ADR-0010), ese texto se migró
aquí **antes** de vaciarlo, para que la trazabilidad no se rompiera justo donde más vale.

Son registro histórico: el texto de cada celda está copiado sin editar, y cada archivo termina con
una sección "Dónde vive esto hoy" que apunta al código actual.

| Archivo | Pregunta que responde | Celdas |
| --- | --- | --- |
| [caso-de-uso-y-posicionamiento.md](caso-de-uso-y-posicionamiento.md) | ¿Por qué este caso merece IA y en qué se diferencia de lo que ya existe? | 0, 5, 7, 9, 10, 12, 35, 37, 39 |
| [correcciones-v1.md](correcciones-v1.md) | ¿Qué estaba roto en la primera versión y cómo se corrigió? | 0 |
| [helper-unico-de-llamada.md](helper-unico-de-llamada.md) | ¿Por qué la llamada al modelo se define una sola vez? | 3 |
| [por-que-el-diagrama-es-determinista.md](por-que-el-diagrama-es-determinista.md) | ¿Por qué el diagrama no se le pide al modelo? | 14, 15, 16 |
| [por-que-el-esquema-se-congela.md](por-que-el-esquema-se-congela.md) | ¿Por qué el esquema lo fija el equipo y el lote es una lista? | 17 |
| [validaciones-deterministas.md](validaciones-deterministas.md) | ¿Por qué la corrección vive en código y no en el prompt? | 21 |
| [por-que-las-regresiones-no-llaman-al-modelo.md](por-que-las-regresiones-no-llaman-al-modelo.md) | ¿Por qué la suite de regresión es determinista y gratis? | 27 |

Las decisiones posteriores a la migración no están aquí sino en [`docs/adr/`](../adr/README.md).

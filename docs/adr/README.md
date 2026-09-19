# Decisiones de arquitectura (ADR)

Cada decisión que cambia cómo está construido QuickDev, o qué se mide, tiene su ADR: contexto,
decisión, consecuencias y alternativas descartadas. Si una decisión no está aquí, no está tomada.

Los números se repartieron por autor para que tres ramas pudieran escribir en paralelo sin editar
un archivo común. Este índice se consolidó al final, cuando ya existían todos.

| ADR | Decisión | Estado | Autor |
| --- | --- | --- | --- |
| [0001](0001-arquitectura-hexagonal.md) | Puertos y adaptadores: la frontera "el modelo interpreta, el código verifica" hecha estructura. Y qué patrones **no** usamos | aceptada | equipo |
| [0002](0002-convenciones-de-codigo-y-contrato.md) | Inglés en el código, español en el contrato JSON; el contrato evoluciona de forma aditiva | aceptada | equipo |
| [0003](0003-una-regla-una-clase.md) | Una regla, una clase; una versión del validador, una composición. El bug de las citas literales | implementada | Edwin |
| [0004](0004-detectar-vs-reparar.md) | `Validator` detecta y `RepairPolicy` corrige; la política de reparación como tabla | implementada | Edwin |
| [0005](0005-evidencia-por-indice.md) | Evidencia por índice: el modelo señala, el código cita y cuenta | campo hecho · regla **pendiente de medir** | Edwin |
| [0006](0006-puerto-llm-y-adaptadores-decorados.md) | Reintento y caché como decoradores del puerto; `FakeLlm` para CI sin red | implementada | Miguel |
| [0007](0007-resultados-versionados-y-manifiesto.md) | Un directorio y un manifiesto por corrida: una medición nueva nunca pisa la anterior | implementada | Miguel |
| [0008](0008-correcciones-al-diagnostico.md) | Las inferencias del diagnóstico que estaban mal derivadas, con el antes y el después | implementada | Miguel |
| [0009](0009-structured-output-del-proveedor.md) | `response_schema` del proveedor en vez de pedir la forma por prompt | implementada · **pendiente de medir** | Miguel |
| [0010](0010-notebook-como-demo-delgada.md) | El notebook como demo de 5 celdas sin lógica; su narrativa migrada a `docs/historia/` | implementada | José |
| [0011](0011-prompts-como-archivos-congelados.md) | Prompts congelados con `sha256`; payload según la versión; `v2` sin medir | implementada · `v2` **pendiente de medir** | José |
| [0012](0012-la-cache-no-se-usa-para-medir.md) | Las corridas de evals en vivo no usan caché: medir es muestrear. Corrige el ADR-0006 | implementada | equipo |

## Lo que está decidido pero no medido

Tres ADRs dejan una hipótesis preparada y declaran que no saben si mejora. No es un descuido: la
regla del equipo es una hipótesis, un cambio, una medición.

- **0005:** usar `evidencia_idx` para que frecuencia y citas las calcule el código.
- **0009:** cuánto mejora la fiabilidad el `response_schema` del proveedor.
- **0011:** si enviar los comentarios como array JSON (`v2`) cambia las tasas.

Las tres necesitan una corrida real contra la API, y hoy no hay una `GEMINI_API_KEY` válida.

## Cómo escribir uno nuevo

Copia la estructura de cualquiera de los anteriores (estado, fecha, quién decide, a qué afecta;
contexto, decisión, consecuencias, alternativas descartadas), usa el siguiente número libre y
añade su fila aquí. Si la decisión cambia algo medido, enlaza la corrida que lo mide.

# ADR-0001 · Arquitectura hexagonal (puertos y adaptadores)

- **Estado:** aceptada
- **Fecha:** 2026-09-14
- **Decide:** equipo Solid
- **Afecta a:** todo el paquete `quickdev/`

## Contexto

QuickDev nació como un Jupyter notebook (`QuickDev_01.ipynb`) más un paquete de
evals (`evals/motor.py`, `evals/casos.py`). En ese estado el repo tenía cuatro
problemas medibles:

1. **Duplicación con divergencia.** `validate_output`, `OUTPUT_SCHEMA` y
   `build_input` estaban escritos dos veces, en el notebook y en `motor.py`, y
   ya habían divergido: la copia del notebook era la versión anterior, sin el
   parámetro `version_esperada` y con un falso positivo que el diagnóstico del
   baseline ya había identificado y corregido en la otra copia. La respuesta a
   "¿el validador atrapa el edge case de versión?" dependía de qué archivo
   abrieras.
2. **Un módulo con seis responsabilidades.** `motor.py` tenía 690 líneas que
   contenían el esquema congelado, el validador, el cliente de Gemini, la
   construcción de prompts, la orquestación de corridas, la inferencia del
   diagnóstico, la escritura de CSV/JSON/Markdown y el parseo de la CLI. Con
   tres personas trabajando, cualquier cambio tocaba ese archivo y todas las
   ramas entraban en conflicto.
3. **Imposible de testear sin cuota.** `get_client()` era un singleton con
   `global _client`, y el SDK de Gemini se importaba dentro del runner. No se
   podía correr el pipeline sin red y sin API key, así que no había CI posible.
4. **Nada era intercambiable.** El validador ramificaba por dentro con
   `modo="baseline"|"after"` (`motor.py:118` y `:183`). La tercera iteración
   habría sido un tercer `if` dentro de la misma función de 110 líneas que el
   baseline usa como referencia de comparación.

## Decisión

Adoptamos **puertos y adaptadores** (arquitectura hexagonal), con la dependencia
apuntando siempre hacia adentro:

```
domain/         el contrato, los modelos y las reglas. PURO.
ports/          las interfaces que el dominio necesita del exterior.
adapters/       las implementaciones concretas.
application/    el caso de uso: ordena los pasos del flujo.
observability/  la traza de cada ejecución.
```

La razón de elegirla **no es que esté de moda**: es que este producto ya tenía su
frontera dibujada antes de que existiera la arquitectura. La tesis del proyecto
es *"el modelo interpreta lenguaje, el código verifica hechos"*, y eso es
literalmente la definición de un dominio puro rodeado de adaptadores. La
arquitectura solo hace explícito lo que el equipo ya había decidido.

Reglas concretas que se derivan y que son verificables:

- `quickdev/domain/**` no importa SDKs, ni `pandas`, ni hace I/O. Verificable:
  `grep -rE "genai|pandas|open\(|requests" quickdev/domain/` debe salir vacío.
- El único archivo del repo que importa `google.genai` es
  `quickdev/adapters/gemini.py`.
- Reintento y caché son **decoradores** del puerto, no responsabilidades del
  cliente: `CachingLlm(RetryingLlm(GeminiAdapter()))`.
- El puerto devuelve `dict`, no `FeedbackReport`. El parseo al dominio ocurre en
  la capa de aplicación. Así los adaptadores no dependen del dominio, y el JSON
  crudo del modelo se conserva intacto para los evals.

## Consecuencias

**El pago inmediato es el `FakeLlm`.** `evals/resultados/baseline/crudo.json` ya
guarda el input y el output de cada corrida. Un adaptador que reproduzca ese JSON
convierte los evals en tests de CI: pipeline completo, sin red, sin API key,
deterministas. El flag `--desde-crudo` que existía como caso especial deja de
serlo y pasa a ser simplemente otro adaptador.

**Tres personas pueden trabajar en paralelo.** El reparto por capa (dominio /
adaptadores / aplicación y documentación) significa que las tres ramas de
`PROMPTS_EQUIPO.md` no comparten ni un archivo.

**Cuesta más archivos.** Lo que era una función de 110 líneas pasa a ser una
docena de clases pequeñas. Es un coste real y consciente: se paga en navegación
y se cobra en que agregar una regla sea agregar un archivo.

**Hay una puerta de aceptación.** El refactor no puede cambiar el
comportamiento medido: correr los evals en modo replay sobre
`baseline/crudo.json` con el conjunto de reglas `baseline` debe reproducir el
`diagnostico.md` ya commiteado. La única excepción esperada está documentada en
ADR-0003 (la regla de citas literales se vuelve más estricta al corregir un bug).

## Alternativas descartadas

**Dejarlo en el notebook y solo limpiar los duplicados.** Habría resuelto el
problema 1 y ninguno de los otros tres. Y el notebook no se puede testear en CI
ni revisar en un PR: el último diff fueron +323 líneas por cinco celdas.

**Arquitectura en capas clásica (presentación / servicios / datos).** No encaja:
aquí no hay base de datos y el "dato" relevante es una respuesta de un modelo
probabilístico. Lo que necesitamos aislar es precisamente al proveedor, y eso es
un puerto, no una capa de datos.

**Un `ValidadorAfter(ValidadorBaseline)` que sobrescriba métodos.** Es la
tentación natural y rompe el principio de sustitución: una subclase que cambia
*cuándo un output aprueba* no es sustituible por su padre. Se descarta en favor
de composición de reglas (ADR-0003).

## Lo que deliberadamente NO hacemos

Anotado aquí para que nadie lo agregue por costumbre, y para poder justificar su
ausencia si alguien pregunta en la sustentación:

- **Sin contenedor de inyección de dependencias.** Las dependencias se pasan por
  constructor. Son tres personas y un caso de uso; un contenedor añade
  indirección sin resolver ningún problema que tengamos hoy.
- **Sin event bus.** No hay nada asíncrono ni ningún consumidor desacoplado.
- **Sin repositorios ni ORM.** No hay persistencia de dominio. Lo que se guarda
  son resultados de evals, y para eso hay escritores de CSV/JSON.
- **Sin abstract factory sobre proveedores.** Tenemos un proveedor. El puerto
  existe para poder testear sin él, no para soportar cinco.

Un patrón que no resuelve un problema que ya sentimos es solo código que hay que
mantener.

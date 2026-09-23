# ADR-0011 · Los prompts son archivos congelados, y el payload depende de la versión

- **Estado:** aceptada e implementada · el prompt `v2` **sin medir**
- **Fecha:** 2026-09-14
- **Decide:** José Díaz (`core/jose`)
- **Afecta a:** `prompts/`, `quickdev/application/prompting.py` (**cambia el Protocol `PromptProvider`**),
  `quickdev/application/analyze_batch.py`, `quickdev/adapters/fake.py`, `evals/runner.py`, `evals/__main__.py`

## Contexto

Los dos prompts medidos (`baseline` y `after`) vivían como strings dentro de `evals/motor.py` y,
tras la reescritura del harness, en el puente temporal `evals/prompts_legacy.py`. Tenían que salir
a `prompts/` para que un cambio de prompt se revisara como lo que es: un cambio de comportamiento.

Al migrarlos aparecieron cuatro problemas:

1. **El prompt era una plantilla.** Interpolaba `evals/contract_frozen.json`, que tiene
   contradicciones pendientes de reconciliar. Reconciliar el contrato habría cambiado en silencio
   el texto con el que se midieron `baseline/` y `after/`.
2. **Nada impedía editar un prompt medido.** Un editor que quite un salto de línea, o un checkout
   de Windows con `autocrlf`, cambia bytes que el modelo lee.
3. **El formato del input es frágil.** Los comentarios viajan como un string numerado
   (`1. (discord) "texto"`): un comentario con comillas y un salto de línea parece dos. Arreglarlo
   cambia lo que recibe el modelo, así que tiene que ser un prompt nuevo, no un parche.
4. **El contrato no podía expresar ese prompt nuevo.** `build_payload(batch)` no recibía la versión,
   y el texto de cada versión se refiere a una forma concreta del input ("la primera línea" en
   `after`). Además, dos sitios del harness suponían que la versión de reglas se llama igual que la
   del prompt (`rules_version or prompt_version`).

## Decisión

1. **Cada `prompts/<version>.md` guarda el prompt ya renderizado**, byte a byte igual al medido, y
   el `context` del payload sale de `prompts/contexto.json`, una copia congelada. El contrato puede
   reconciliarse mañana sin tocar una medición.
2. **Front matter con `sha256`, comprobado al cargar.** `PromptRegistry` normaliza `\r\n` y verifica
   el hash; si no coincide, falla con un mensaje que dice lo que hay que hacer: una versión nueva es
   un archivo nuevo. Los hashes de `baseline` y `after` están fijados en
   `tests/application/test_prompting.py`, calculados sobre el texto legacy antes de borrarlo, y el
   input se compara contra el que el modelo recibió de verdad (`crudo.json`).
3. **El front matter declara `rules_version` y `payload`.** Con qué reglas se mide la versión y en
   qué forma viaja el lote son parte de lo que se midió con ese texto.
4. **`build_payload(batch, version)`.** La forma del payload la decide la versión. Es un cambio del
   Protocol compartido: se actualizaron `AnalyzeBatch`, el runner y el doble de
   `tests/application/test_analyze_batch.py`.
5. **`v2`, sin medir y fuera del default.** Es `after` con una sola hipótesis nueva: los comentarios
   viajan como `input.comentarios[{idx, fuente, texto}]` y la build como `input.build`. Solo se
   reescriben las dos reglas del texto que citaban "la primera línea del input", que con el formato
   nuevo serían falsas. Un test falla si alguien toca otra regla de `v2`. No se quitan las
   instrucciones de formato que ADR-0009 considera redundantes: esa sería una segunda hipótesis en
   la misma medición. `Settings.prompt_version` sigue en `after`.
6. **Grabar y reproducir usan la misma clave.** `FakeLlm.key_for_payload` la calculan el runner al
   escribir `crudo.json` y el `FakeLlm` al buscar. Sin eso, una corrida de `v2` (cuyo `input` no es
   un string) no se habría podido reproducir nunca.
7. **Un replay sin ninguna corrida con esa forma de input falla antes de correr.** Antes,
   `python -m evals --modo v2 --replay evals/resultados/after/crudo.json` salía con código 0 y un
   diagnóstico de **0/15**: una medición falsa de un prompt que nunca se midió. Si faltan solo
   algunos casos (lo normal al agregar un eval) no falla: esos casos salen como corridas muertas,
   visibles en su fila.

## Consecuencias

- Los prompts se leen, se diffean y se revisan como texto. Un cambio accidental no pasa `pytest`.
- `v2` solo se puede medir contra la API: `quickdev eval --prompt v2 --n 10`, comparando contra
  `evals/resultados/after/`. Hasta entonces el README y el CHANGELOG lo declaran sin medir.
- `config.py` **no** valida `prompt_version`, a propósito: obligaría a `config` a importar
  `application`, que ya depende de `config`. Una versión inexistente falla en `render_prompt`, el
  primer paso del pipeline, antes de cualquier llamada a la API; y las CLIs la limitan con `choices`.
- La CLI y el harness dependen de que `prompts/` esté en la raíz del repo: funcionan con
  `pip install -e .`, no desde un wheel.
- Editar un prompt medido "solo para arreglar una errata" ya no es posible sin cambiar su hash, y
  eso es deliberado.

## Alternativas descartadas

**Guardar solo las reglas en `prompts/` y seguir renderizando la plantilla.** Diff más pequeño, pero
el texto medido dependería de `contract_frozen.json`, que todo el mundo sabe que hay que cambiar.

**Cambiar el formato del payload directamente en `after`.** Invalida la comparación con las
mediciones commiteadas y rompe el replay de las 30 corridas.

**Un `PromptRegistry(payload_version=...)` en vez de cambiar el Protocol.** Evita tocar el contrato,
pero crea dos fuentes para la versión (la del registro y `Settings.prompt_version`) que pueden no
coincidir, y ese desajuste emparejaría un texto con la forma de input equivocada sin que nada
fallara.

**Medir `v2` antes de commitearlo.** Es lo correcto, y no fue posible: no hay una `GEMINI_API_KEY`
válida en el equipo. Se decidió dejarlo preparado y declarado como no medido en vez de esperar;
medirlo es la siguiente tarea en cuanto haya clave.

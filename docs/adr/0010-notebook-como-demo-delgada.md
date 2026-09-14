# ADR-0010 · El notebook como demo delgada

- **Estado:** aceptada e implementada
- **Fecha:** 2026-09-14
- **Decide:** José Díaz (`core/jose`), sobre la decisión D1 del plan del equipo
- **Afecta a:** `QuickDev_01.ipynb`, `docs/historia/`, `.gitattributes`, `pyproject.toml` (`[tool.ruff]`)

## Contexto

`QuickDev_01.ipynb` fue el producto entero: 40 celdas con el esquema, el cliente de Gemini, los
prompts, `validate_output`, las pruebas adversariales, las regresiones y el pitch. Eso produjo tres
problemas medibles:

1. **Dos fuentes de verdad que divergieron.** `validate_output`, `OUTPUT_SCHEMA` y `build_input`
   existían en el notebook y en `evals/motor.py`. La copia del notebook era la vieja, con el falso
   positivo de `version_juego`. La respuesta a "¿el validador atrapa el edge case?" dependía de qué
   archivo abrieras.
2. **El comportamiento dependía del orden de ejecución.** La celda 3 lo documenta:
   `ask_gemini_json` llegó a estar definida tres veces, y el resultado dependía de cuál se hubiera
   ejecutado de último.
3. **Reviews ilegibles.** El último diff del notebook antes de la migración fueron +323 líneas por
   cinco celdas, casi todo outputs. Entre tres personas, eso no se revisa: se aprueba a ciegas.

Y un cuarto, que no era un bug pero sí un riesgo: el **por qué** de las primeras decisiones del
proyecto solo existía en sus celdas markdown. Vaciar el notebook sin migrar ese texto habría roto
la trazabilidad justo donde más vale.

## Decisión

1. **La narrativa se migra antes de vaciar.** Cada argumento del notebook va a su archivo en
   `docs/historia/`, copiado sin editar y citando la celda de origen, con una sección "Dónde vive
   esto hoy" que apunta al código actual. Fue el primer commit de la rama, antes de tocar el
   notebook.
2. **El notebook queda en 5 celdas y cero lógica.** Una de introducción y cuatro de código:
   el lote, el pipeline completo, lo que decide el código (hallazgos, revisión humana, traza) y un
   caso roto a propósito (un total inventado de 214) que el validador atrapa y corrige. Sin `def`,
   sin `!pip`, sin `google.colab`. Todo se importa de `quickdev`, y la composición es la misma que
   usa `quickdev demo` (`quickdev.cli.construir_analisis`).
3. **Corre sin API key y sin red**, con `FakeLlm` sobre `evals/resultados/after/crudo.json`. La
   sustentación no depende del wifi.
4. **Los outputs no entran al repo.** `nbstripout` como filtro de git (`.gitattributes`), activado
   una vez por clon con `nbstripout --install`. El archivo commiteado ya está en el punto fijo del
   filtro y de `ruff format`, así que ninguno de los dos genera diffs espurios.
5. **El notebook deja de estar exento de ruff.** La exclusión existía por sus 28 violaciones
   preexistentes; al vaciarlo, se borró en el mismo commit.

## Consecuencias

- Hay **una sola implementación** de cada cosa. Cambiar el validador cambia la demo, los evals y
  la CLI a la vez, porque los tres importan lo mismo.
- El notebook se puede ejecutar de arriba abajo en cualquier orden de lectura: no define estado
  que otra celda redefina.
- Lo que el notebook ya no hace: las Partes 1-3 y 9-10 (reality check, crítica del caso con el
  modelo, comparación de ideas y pitch) eran ejercicios de selección del caso, no parte del
  producto. Su texto está en `docs/historia/caso-de-uso-y-posicionamiento.md`; su código no se migró.
- `build_mermaid` (celda 15) tampoco se migró. Generaba el diagrama desde el contrato que
  produjo el modelo, hoy congelado en `evals/contract_frozen.json`, y ese archivo contradice al
  código en dos puntos. Regenerar el diagrama desde ahí publicaría esas contradicciones. El
  diagrama vigente se mantiene a mano en `docs/arquitectura.md` y `README.md`, contra el código
  real; el código original queda como registro en `docs/historia/por-que-el-diagrama-es-determinista.md`.
- Coste: quien no ejecute `nbstripout --install` puede volver a commitear outputs. No rompe nada,
  pero ensucia el diff; está en el README.

## Alternativas descartadas

**Borrar el notebook.** Se descarta: es la pieza de la sustentación y la entrada más amable para
alguien que llega al repo. El problema nunca fue que existiera, sino que contuviera el sistema.

**Dejar el notebook con su lógica y marcarlo como "legacy".** Se descarta: conserva exactamente la
segunda fuente de verdad que causó la divergencia, y nadie puede saber qué celda sigue siendo
cierta.

**Vaciarlo y dejar el razonamiento en el historial de git.** Se descarta: `git log` no es
documentación. Quien pregunte "¿por qué el lote es una lista y no una frase?" no va a buscar en un
diff de hace tres semanas.

**Commitear los outputs para que la demo se vea sin ejecutar.** Se descarta: es lo que producía
los diffs de +323 líneas, y los outputs de una ejecución con modelo cambian entre corridas. La demo
sin red se puede ejecutar en segundos, así que no hace falta guardarlos.

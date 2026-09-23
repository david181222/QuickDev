"""Trazabilidad de la ejecucion, en dos piezas con responsabilidades distintas.

- `trace.py`    la traza de UNA ejecucion del pipeline: que paso, en que orden,
                con que decision. Dato puro, sin I/O. Lo dejo el Paso 0.
- `manifest.py` el estampado de UNA corrida de evals: que versiones, que commit,
                cuantas llamadas y cuanto costaron. Escribe a disco y averigua el
                `git_sha`, y es lo unico del paquete que hace `subprocess`.

Estan separados porque responden a preguntas distintas. El `Trace` responde «por
que este reporte salio asi»; el `RunManifest` responde «que produjo estos
numeros». Y porque el primero tiene que poder vivir dentro del dominio sin tocar
el sistema de archivos. Ver ADR-0007.
"""

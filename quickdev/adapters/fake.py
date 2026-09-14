"""El adaptador que no llama a nadie: reproduce outputs ya medidos.

Responsabilidad: devolver, ante la misma entrada, exactamente el JSON que el
modelo devolvio el dia que se midio.

Lo que NO le corresponde: inventar respuestas. Si le piden algo que no tiene
grabado, falla ruidosamente. Ver "por que grita" mas abajo.

## Que es esta pieza

Es el pago inmediato de la arquitectura hexagonal. El flag `--desde-crudo` que
tenia `evals/motor.py` era un caso especial dentro del bucle de corrida: un `if`
que decidia si se llamaba a la API o se leia un archivo. Aqui deja de ser un caso
especial y pasa a ser simplemente otro adaptador del mismo puerto, y con el, el
pipeline COMPLETO (prompt, validacion, reparacion, diagnostico, reportes) corre
en CI sin red, sin API key y sin cuota, de forma determinista.

## Por que grita cuando falta una corrida

Porque `evals/motor.py:429-431` hacia `continue` en silencio cuando faltaba un
registro, y `n = len(filas)` se encogia sin que nadie se enterara. Una tasa de
"2/2" y una de "2/3" se leen igual de bien en un informe y no significan lo
mismo: la primera puede ser una corrida a la que le falto un dato. Aqui, pedir
una corrida que no existe es un error y se ve.
"""

import json
from pathlib import Path

from quickdev.ports.llm import LlmRequest, LlmResponse, LlmTerminalError


class SinRespuestaGrabada(LlmTerminalError):
    """Se pidio una respuesta que no esta en el archivo de corridas guardadas."""


class FakeLlm:
    """Implementa `LlmPort` leyendo respuestas grabadas.

    Las respuestas se indexan por el texto del input, que es lo unico que
    identifica una corrida en `crudo.json`. Cada clave guarda la LISTA de
    corridas en orden (run1, run2, run3...) y cada llamada consume la siguiente,
    de forma que n llamadas sobre el mismo caso reproducen las n corridas
    medidas, incluida su variabilidad. Eso importa: si las n llamadas devolvieran
    siempre run1, la pregunta de diagnostico "el resultado es inestable entre
    corridas?" siempre respondaria NO en replay, que es justo la senal que se
    quiere conservar.
    """

    def __init__(self, respuestas: dict[str, list[dict]], model: str = "replay") -> None:
        """
        Args:
            respuestas: input grabado -> lista de outputs crudos, en orden.
            model: lo que se estampa en `LlmResponse.model`. Por defecto
                "replay", para que ningun reporte pueda confundir una corrida
                reproducida con una medicion nueva.
        """
        self.respuestas = respuestas
        self.model = model
        self._consumidas: dict[str, int] = {}

    # -- construccion --------------------------------------------------------

    @classmethod
    def from_crudo(cls, archivo: Path, model: str = "replay") -> "FakeLlm":
        """Carga un `evals/resultados/<modo>/crudo.json`.

        El formato es `{"<eval_id>_run<i>": {"input": ..., "output_crudo": ...}}`.
        Las claves se agrupan por input y se ordenan por numero de corrida, no
        alfabeticamente: con 10 corridas, el orden alfabetico pone run10 antes
        que run2 y el replay dejaria de seguir el orden medido.
        """
        archivo = Path(archivo)
        crudo = json.loads(archivo.read_text(encoding="utf-8"))

        entradas = sorted(crudo.items(), key=lambda kv: _orden_de_corrida(kv[0]))
        respuestas: dict[str, list[dict]] = {}
        for _clave, registro in entradas:
            entrada = registro.get("input")
            salida = registro.get("output_crudo")
            if entrada is None or salida is None:
                continue
            respuestas.setdefault(entrada, []).append(
                {"output": salida, "meta": registro.get("meta_tool") or {}}
            )
        if not respuestas:
            raise SinRespuestaGrabada(
                f"{archivo} no contiene ninguna corrida con input y output_crudo."
            )
        return cls(respuestas, model=model)

    # -- el puerto -----------------------------------------------------------

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        """La siguiente corrida grabada para ese input.

        Raises:
            SinRespuestaGrabada: no hay nada grabado para ese input, o ya se
                consumieron todas las corridas que habia.
        """
        clave = self.key(request)
        grabadas = self.respuestas.get(clave)
        if grabadas is None:
            raise SinRespuestaGrabada(
                f"No hay ninguna corrida grabada para este input. "
                f"Inputs disponibles: {len(self.respuestas)}. "
                f"Empieza por: {clave[:80]!r}"
            )

        i = self._consumidas.get(clave, 0)
        if i >= len(grabadas):
            raise SinRespuestaGrabada(
                f"Se pidieron {i + 1} corridas de este input pero solo hay "
                f"{len(grabadas)} grabadas. En replay, n no puede ser mayor que "
                f"el numero de corridas medidas: baja n o vuelve a medir. "
                f"Input: {clave[:80]!r}"
            )
        self._consumidas[clave] = i + 1

        registro = grabadas[i]
        salida = registro["output"]
        meta = registro["meta"]
        return LlmResponse(
            data=salida,
            raw_text=json.dumps(salida, ensure_ascii=False),
            attempts=int(meta.get("intentos", 1) or 1),
            truncated=bool(meta.get("truncado", False)),
            latency_s=float(meta.get("latencia_s", 0.0) or 0.0),
            from_cache=False,
            model=self.model,
        )

    @staticmethod
    def key(request: LlmRequest) -> str:
        """Que identifica una corrida grabada.

        El texto del input, cuando el payload lo trae bajo la clave "input" (que
        es la forma con la que se midieron `baseline/` y `after/`). Si algun dia
        el payload cambia de forma, se cae al JSON canonico completo, que sigue
        siendo estable pero ya no casa con los archivos viejos. Ese cambio de
        forma es un cambio de comportamiento y hay que medirlo, no deslizarlo.
        """
        entrada = request.payload.get("input")
        if isinstance(entrada, str):
            return entrada
        return json.dumps(request.payload, ensure_ascii=False, sort_keys=True)

    # -- utilidades ----------------------------------------------------------

    @property
    def corridas_por_input(self) -> dict[str, int]:
        """Cuantas corridas hay grabadas de cada input. Util para elegir n."""
        return {k: len(v) for k, v in self.respuestas.items()}

    @property
    def max_corridas(self) -> int:
        """El n mas alto que este archivo puede reproducir sin quedarse corto."""
        if not self.respuestas:
            return 0
        return min(len(v) for v in self.respuestas.values())

    def reset(self) -> None:
        """Vuelve a empezar por run1. Para reutilizar el mismo fake en otro caso."""
        self._consumidas.clear()


def _orden_de_corrida(clave: str) -> tuple[str, int]:
    """Ordena `caso_run2` antes que `caso_run10`, que alfabeticamente van al reves."""
    caso, _, corrida = clave.rpartition("_run")
    if not caso or not corrida.isdigit():
        return (clave, 0)
    return (caso, int(corrida))

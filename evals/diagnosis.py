"""Las 7 preguntas de diagnostico, derivadas del comportamiento observado.

Responsabilidad: convertir las filas de una corrida en respuestas con evidencia.

Lo que NO le corresponde: correr nada (`runner.py`) ni darle formato (
`reporting.py`).

La idea que hay que conservar de la version vieja, porque es lo mejor que tiene
este harness: cada asercion se evalua DOS veces, contra el output crudo del
modelo y contra el output ya corregido por el validador. La diferencia entre las
dos lecturas es lo que separa "fallo el prompt" (fallo en crudo, lo salvo el
codigo) de "falto validacion" (fallo en crudo y sigue fallando despues).

## Las seis inferencias que se arreglaron

Cada una con la linea original como evidencia. Estan desarrolladas en el
ADR-0008; aqui va el resumen, junto al codigo que las implementa.

1. `motor.py:374` marcaba `tool_ok=False` ante cualquier reintento. Un happy path
   de 3/3 que tropezo con un rate limit se reportaba como fallo de la tool.
   Ahora reintentar y fallar son dos cosas distintas y se cuentan aparte.
2. `motor.py:500` derivaba "elegimos mal el modelo?" de `0 < fallos < n` con
   n=3. Uno de tres no distingue un flake de un defecto. Ahora el umbral es
   explicito y configurable, y por debajo de `min_corridas` la pregunta responde
   SIN DATO en vez de inventarse una respuesta.
3. `motor.py:512` derivaba "falto contexto?" de un SUBCONJUNTO de lo que usaba
   para "fallo el prompt?", asi que no son independientes. Ahora se declara
   derivada en vez de presentarse como una segunda senal.
4. `motor.py:409-410` convertia cualquier excepcion de una asercion en `False`.
   Ahora existe el estado ERROR: una asercion rota es culpa nuestra, no un
   hallazgo sobre el modelo.
5. `motor.py:429-431` encogia n en silencio si faltaba una corrida. Ahora falla
   ruidosamente (en `adapters/fake.py`) y ademas `n` viaja explicito hasta aqui.
6. La respuesta deja de ser binaria: hay preguntas que con los datos de una
   corrida no se pueden responder, y decirlo es mas defendible que elegir NO.
"""

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from evals.cases import CAUSAS, EvalCase, Resultado

# Estado de una asercion a lo largo de la corrida completa.
OK = "ok"
SALVADO = "salvado_por_codigo"
NO_DETECTADO = "no_detectado"
ERROR_DE_ASERCION = "error_de_asercion"


class Respuesta(StrEnum):
    """Tres valores, no dos.

    SIN_DATO no es una cortesia: es la diferencia entre "medimos y no pasa" y "no
    teniamos con que medirlo". Un diagnostico que nunca dice SIN DATO esta
    respondiendo preguntas que no puede responder.
    """

    SI = "SÍ"
    NO = "NO"
    SIN_DATO = "SIN DATO"


@dataclass(frozen=True)
class Umbrales:
    """Cuando una diferencia entre corridas es senal y cuando es ruido.

    Esto existe porque `0 < x < n` no es un umbral, es la ausencia de uno: con
    n=3, un unico fallo bastaba para afirmar que el modelo era inestable.

    - `min_corridas`: por debajo de esto, la pregunta sobre estabilidad no se
      responde. Con 3 corridas no se distingue un flake de un defecto, y esa es
      la pregunta mas cara del diagnostico.
    - `fraccion_minima`: que parte de las corridas tiene que desviarse para que
      cuente. Con 10 corridas y `0.2`, un solo fallo (0.1) es ruido; dos ya son
      senal.
    """

    min_corridas: int = 5
    fraccion_minima: float = 0.2


UMBRALES_POR_DEFECTO = Umbrales()


@dataclass(frozen=True)
class Pregunta:
    """Una respuesta con su evidencia, y si se derivo de otra."""

    respuesta: Respuesta
    evidencia: str
    derivada_de: str = ""

    def to_dict(self) -> dict:
        d = {"respuesta": str(self.respuesta), "evidencia": self.evidencia}
        if self.derivada_de:
            d["derivada_de"] = self.derivada_de
        return d


# ---------------------------------------------------------------------------


def _contar(filas: list[dict], case: EvalCase) -> dict[str, dict]:
    """Agrega, por asercion, como fue en crudo y como fue tras el validador."""
    causa_de = {a.nombre: a.causa for a in case.asserts}
    desc_de = {a.nombre: a.descripcion for a in case.asserts}
    acc = defaultdict(
        lambda: {"evaluadas": 0, "crudo_fail": 0, "crudo_error": 0, "corr_fail": 0}
    )

    for f in filas:
        for nombre, estado in (f.get("asserts_crudo") or {}).items():
            acc[nombre]["evaluadas"] += 1
            if estado == Resultado.FALLA:
                acc[nombre]["crudo_fail"] += 1
            elif estado == Resultado.ERROR:
                acc[nombre]["crudo_error"] += 1
        for nombre, estado in (f.get("asserts_corregido") or {}).items():
            if estado == Resultado.FALLA:
                acc[nombre]["corr_fail"] += 1

    detalle = {}
    for nombre, d in acc.items():
        if d["crudo_error"]:
            estado = ERROR_DE_ASERCION
        elif d["crudo_fail"] == 0:
            estado = OK
        elif d["corr_fail"] > 0:
            estado = NO_DETECTADO
        else:
            estado = SALVADO
        detalle[nombre] = {
            "causa": causa_de.get(nombre),
            "descripcion": desc_de.get(nombre),
            "fallos_en_crudo": f"{d['crudo_fail']}/{d['evaluadas']}",
            "fallos_tras_validar": f"{d['corr_fail']}/{d['evaluadas']}",
            "errores": d["crudo_error"],
            "estado": estado,
            "_n_fallos": d["crudo_fail"],
            "_n_evaluadas": d["evaluadas"],
        }
    return detalle


def _inestable(d: dict, umbrales: Umbrales) -> bool:
    """La asercion pasa en unas corridas y falla en otras, por encima del umbral."""
    n, fallos = d["_n_evaluadas"], d["_n_fallos"]
    if n == 0 or fallos == 0 or fallos == n:
        return False
    desviacion = min(fallos, n - fallos) / n
    return desviacion >= umbrales.fraccion_minima


def diagnosticar(
    case: EvalCase,
    filas: list[dict],
    n_esperado: int,
    umbrales: Umbrales = UMBRALES_POR_DEFECTO,
) -> dict:
    """Las 7 respuestas para un eval.

    Args:
        case: el eval.
        filas: una por corrida, ya evaluadas.
        n_esperado: cuantas corridas se pidieron. Se compara con las que hay: si
            no coinciden, el diagnostico lo dice en vez de encoger n.
        umbrales: cuando una diferencia entre corridas cuenta como senal.
    """
    n = len(filas)
    detalle = _contar(filas, case)

    def por_causa(seleccion: dict, causa: str) -> list[str]:
        return sorted(k for k, v in seleccion.items() if v["causa"] == causa)

    fallos_crudo = {k: v for k, v in detalle.items() if v["_n_fallos"] > 0}
    no_detectados = {k: v for k, v in detalle.items() if v["estado"] == NO_DETECTADO}
    con_error = {k: v for k, v in detalle.items() if v["estado"] == ERROR_DE_ASERCION}
    inestables = {k: v for k, v in detalle.items() if _inestable(v, umbrales)}
    consistentes = {
        k: v for k, v in detalle.items() if n > 0 and v["_n_fallos"] == v["_n_evaluadas"] > 0
    }

    p_prompt = por_causa(fallos_crudo, "prompt")
    p_schema = por_causa(fallos_crudo, "schema")
    p_hitl = por_causa(fallos_crudo, "hitl")
    p_ctx = por_causa(consistentes, "prompt") + por_causa(consistentes, "hitl")

    preguntas = {
        CAUSAS["prompt"]: _pregunta_prompt(p_prompt),
        CAUSAS["contexto"]: _pregunta_contexto(p_ctx, n),
        CAUSAS["schema"]: _pregunta_schema(p_schema),
        CAUSAS["tool"]: _pregunta_tool(filas, n),
        CAUSAS["validacion"]: _pregunta_validacion(no_detectados),
        CAUSAS["modelo"]: _pregunta_modelo(inestables, n, umbrales),
        CAUSAS["hitl"]: _pregunta_hitl(case, p_hitl),
    }

    return {
        "eval_id": case.id,
        "categoria": case.categoria,
        "hipotesis": case.hipotesis,
        "corridas": n,
        "corridas_esperadas": n_esperado,
        "corridas_completas": n == n_esperado,
        "tasa": f"{sum(1 for f in filas if f.get('paso')) }/{n}",
        "detalle_asserts": {k: _sin_privados(v) for k, v in detalle.items()},
        "errores_de_asercion": sorted(con_error),
        "umbrales": {
            "min_corridas": umbrales.min_corridas,
            "fraccion_minima": umbrales.fraccion_minima,
        },
        "preguntas": {k: v.to_dict() for k, v in preguntas.items()},
    }


def _sin_privados(v: dict) -> dict:
    return {k: x for k, x in v.items() if not k.startswith("_")}


# ---------------------------------------------------------------------------
# Las siete preguntas, una funcion cada una
# ---------------------------------------------------------------------------


def _pregunta_prompt(fallidas: list[str]) -> Pregunta:
    if fallidas:
        return Pregunta(Respuesta.SI, f"fallaron en el output crudo: {fallidas}")
    return Pregunta(
        Respuesta.NO, "ninguna aserción atribuida al prompt falló en el output crudo"
    )


def _pregunta_contexto(consistentes: list[str], n: int) -> Pregunta:
    """DERIVADA de "fallo el prompt?". No es una segunda senal independiente.

    `motor.py:512` la calculaba sobre un subconjunto estricto de lo que usaba
    para la pregunta del prompt, asi que nunca podia dar SI si aquella daba NO.
    Presentarlas como dos senales infla la sensacion de evidencia. Se conserva
    porque distingue una cosa util -fallo SIEMPRE, luego la instruccion falta o
    es ambigua, no es varianza- pero se declara derivada.
    """
    if consistentes:
        return Pregunta(
            Respuesta.SI,
            f"falló en {n}/{n} corridas, siempre: la instrucción falta o es ambigua, "
            f"no es varianza: {consistentes}",
            derivada_de=CAUSAS["prompt"],
        )
    return Pregunta(
        Respuesta.NO,
        "no hay fallos consistentes en todas las corridas",
        derivada_de=CAUSAS["prompt"],
    )


def _pregunta_schema(fallidas: list[str]) -> Pregunta:
    if fallidas:
        return Pregunta(
            Respuesta.SI, f"el esquema aceptó valores que el contrato prohíbe: {fallidas}"
        )
    return Pregunta(
        Respuesta.NO, "el output respetó forma, enums y rangos del esquema congelado"
    )


def _pregunta_tool(filas: list[dict], n: int) -> Pregunta:
    """Reintentar NO es fallar. El arreglo de `motor.py:374`.

    La tool devolvio mal si murio o si se trunco. Que haya hecho falta un
    segundo intento es un dato de coste, no un defecto, y va en la evidencia
    aparte para que se pueda leer sin confundirlo con un fallo.
    """
    fallidas = [f for f in filas if not f.get("tool_ok", True) or f.get("truncado")]
    reintentos = sum(max(0, f.get("intentos", 1) - 1) for f in filas)
    nota = f" Hubo {reintentos} reintento(s), que no cuentan como fallo." if reintentos else ""

    if fallidas:
        return Pregunta(
            Respuesta.SI,
            f"la capa de llamada falló o truncó en {len(fallidas)}/{n} corridas.{nota}",
        )
    return Pregunta(
        Respuesta.NO, f"JSON válido y completo en {n}/{n} corridas, sin truncamiento.{nota}"
    )


def _pregunta_validacion(no_detectados: dict) -> Pregunta:
    if no_detectados:
        return Pregunta(
            Respuesta.SI,
            f"fallaron en crudo Y siguieron fallando tras el validador: "
            f"{sorted(no_detectados)}",
        )
    return Pregunta(
        Respuesta.NO,
        "todo lo que falló en crudo fue corregido por el código, o no hubo fallos",
    )


def _pregunta_modelo(inestables: dict, n: int, umbrales: Umbrales) -> Pregunta:
    """La pregunta mas cara del diagnostico, y la que peor estaba derivada.

    Con n por debajo del minimo no se responde. Es el arreglo de `motor.py:500`:
    `0 < fallos < 3` llamaba inestable a un unico fallo de tres corridas, que es
    indistinguible de un flake.
    """
    if n < umbrales.min_corridas:
        return Pregunta(
            Respuesta.SIN_DATO,
            f"{n} corridas no bastan para separar un flake de un defecto "
            f"(hacen falta {umbrales.min_corridas}). Sube n: cada corrida es una llamada "
            f"real al modelo, sin caché (ADR-0012).",
        )
    if inestables:
        return Pregunta(
            Respuesta.SI,
            f"resultado inestable entre corridas con temperature=0, por encima del "
            f"umbral de {umbrales.fraccion_minima:.0%}: {sorted(inestables)}",
        )
    return Pregunta(
        Respuesta.NO,
        f"comportamiento estable en las {n} corridas, dentro del umbral de "
        f"{umbrales.fraccion_minima:.0%}",
    )


def _pregunta_hitl(case: EvalCase, fallidas: list[str]) -> Pregunta:
    if not case.exige_hitl:
        return Pregunta(Respuesta.NO, "este caso no exige revisión humana por diseño")
    if fallidas:
        return Pregunta(
            Respuesta.SI,
            f"sí, y el modelo NO la marcó solo ({fallidas}): la forzó el código",
        )
    return Pregunta(
        Respuesta.SI,
        "sí, el caso exige confirmación humana y el modelo la marcó por su cuenta",
    )

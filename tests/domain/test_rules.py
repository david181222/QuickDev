"""Una regla, dos tests: uno que la dispara y otro que confirma que no ladra sola.

El segundo es el que faltaba en el validador original, y es la razon de que su
falso positivo de `version_juego` viviera sin detectarse: habia tests de que la
regla saltaba, ninguno de que no saltara cuando no debia.
"""

from conftest import BASURA, BUG_PARED, BUILD, CITA_V05, JEFE_FINAL, problema

from quickdev.domain.rules.citations import QuotesAreLiteral
from quickdev.domain.rules.counts import FrequencyWithinTotal, TotalMatchesBatch
from quickdev.domain.rules.review import (
    AnyDiscardRequiresReview,
    DiscardedBiasRequiresReview,
    MultipleBuildsRequireReview,
)
from quickdev.domain.rules.versioning import (
    VersionAppearsLiterally,
    VersionIsAnalyzedBuild,
    VersionIsNotNull,
)


def correr(regla, report, batch) -> list:
    return list(regla.check(report, batch))


# ---------------------------------------------------------------------------
# counts.py
# ---------------------------------------------------------------------------


class TestTotalMatchesBatch:
    def test_dispara_cuando_el_total_no_cuadra(self, lote, reporte):
        batch = lote()
        hallazgos = correr(
            TotalMatchesBatch(), reporte(batch, total_comentarios_analizados=99), batch
        )
        assert len(hallazgos) == 1
        assert hallazgos[0].rule_id == "total_matches_batch"
        assert "el lote tiene 2" in hallazgos[0].message

    def test_callada_cuando_el_total_es_el_real(self, lote, reporte):
        batch = lote()
        assert correr(TotalMatchesBatch(), reporte(batch), batch) == []


class TestFrequencyWithinTotal:
    def test_dispara_cuando_la_frecuencia_supera_el_total(self, lote, reporte):
        batch = lote()
        report = reporte(batch, problemas_detectados=[problema(frecuencia=99)])
        hallazgos = correr(FrequencyWithinTotal(), report, batch)
        assert len(hallazgos) == 1
        assert "supera el total 2" in hallazgos[0].message

    def test_callada_cuando_la_frecuencia_cabe(self, lote, reporte):
        batch = lote()
        report = reporte(batch, problemas_detectados=[problema(frecuencia=2)])
        assert correr(FrequencyWithinTotal(), report, batch) == []


# ---------------------------------------------------------------------------
# citations.py
# ---------------------------------------------------------------------------


class TestQuotesAreLiteral:
    def test_dispara_con_una_cita_inventada(self, lote, reporte):
        batch = lote()
        report = reporte(
            batch,
            comentarios_evidencia=[
                {"texto": "Los jugadores estan molestos con el guardado.", "fuente": "discord"}
            ],
        )
        hallazgos = correr(QuotesAreLiteral(), report, batch)
        assert len(hallazgos) == 1
        assert "no existe en el lote" in hallazgos[0].message

    def test_callada_con_una_cita_literal(self, lote, reporte):
        batch = lote()
        report = reporte(batch, comentarios_evidencia=[{"texto": BUG_PARED, "fuente": "discord"}])
        assert correr(QuotesAreLiteral(), report, batch) == []

    def test_dispara_con_una_cita_que_ENVUELVE_un_comentario_real(self, lote, reporte):
        """El bug que arreglamos. El validador viejo dejaba pasar esto.

        `evals/motor.py:164` aceptaba tambien `real in t`, asi que una cita que
        contiene un comentario real mas texto inventado alrededor validaba. Es
        justo lo que "citas literales" promete impedir: el desarrollador no puede
        volver al comentario original porque nadie escribio esa frase.
        """
        batch = lote()
        envuelta = f"Segun varios testers: {BUG_PARED} Y ademas el juego crashea."
        report = reporte(batch, comentarios_evidencia=[{"texto": envuelta, "fuente": "discord"}])
        assert len(correr(QuotesAreLiteral(), report, batch)) == 1

    def test_tolera_comillas_y_espacios_de_mas(self, lote, reporte):
        """Normalizar no afloja la regla: la misma cita con otro formato es la misma."""
        batch = lote()
        con_ruido = '  "' + BUG_PARED.replace(" ", "  ") + '"  '
        report = reporte(batch, comentarios_evidencia=[{"texto": con_ruido, "fuente": "discord"}])
        assert correr(QuotesAreLiteral(), report, batch) == []

    def test_revisa_tambien_los_descartados(self, lote, reporte):
        batch = lote(textos=(BUG_PARED, BASURA))
        report = reporte(
            batch,
            comentarios_descartados=[{"texto": "algo que nadie dijo", "motivo": "ruido"}],
        )
        hallazgos = correr(QuotesAreLiteral(), report, batch)
        assert len(hallazgos) == 1
        assert hallazgos[0].message.startswith("descartado 0")


# ---------------------------------------------------------------------------
# versioning.py
# ---------------------------------------------------------------------------


class TestVersionAppearsLiterally:
    def test_dispara_con_una_version_inventada(self, lote, reporte):
        batch = lote()
        hallazgos = correr(VersionAppearsLiterally(), reporte(batch, version_juego="v9.9.9"), batch)
        assert len(hallazgos) == 1
        assert "no aparece literalmente" in hallazgos[0].message

    def test_callada_cuando_la_version_es_la_build_del_lote(self, lote, reporte):
        batch = lote()
        assert correr(VersionAppearsLiterally(), reporte(batch), batch) == []

    def test_callada_cuando_la_version_esta_dentro_de_un_comentario(self, lote, reporte):
        """Aparecer literalmente no implica ser la build analizada.

        Este es el hueco del baseline: la v0.5 citada por un jugador SI aparece
        en el input, asi que esta regla no puede atraparla. La que si puede es
        `VersionIsAnalyzedBuild`, y solo existe en el conjunto `after`.
        """
        batch = lote(textos=(BUG_PARED, CITA_V05))
        assert correr(VersionAppearsLiterally(), reporte(batch, version_juego="v0.5"), batch) == []


class TestVersionIsNotNull:
    def test_dispara_cuando_la_version_es_null(self, lote, reporte):
        batch = lote()
        hallazgos = correr(VersionIsNotNull(), reporte(batch, version_juego=None), batch)
        assert len(hallazgos) == 1
        assert hallazgos[0].message == "version_juego es null"

    def test_callada_cuando_hay_version(self, lote, reporte):
        batch = lote()
        assert correr(VersionIsNotNull(), reporte(batch), batch) == []

    def test_FALSO_POSITIVO_conservado_cuando_el_lote_no_trae_build(self, lote, reporte):
        """Comportamiento incorrecto, preservado a proposito.

        Un lote sin build declarada legitimamente no tiene version, asi que
        `version_juego = null` es la respuesta CORRECTA. El baseline lo marca
        como fallo igualmente. Ese ruido aparecia en 4 de los 5 evals y tapaba
        los fallos reales; es lo que el diagnostico descubrio y lo que el
        conjunto `after` corrige.

        Se conserva porque `baseline` es el registro de lo que se midio. Si algun
        dia este test empieza a fallar, alguien "arreglo" el baseline y la
        comparacion con `after` dejo de significar nada.
        """
        batch = lote(build=None)
        assert len(correr(VersionIsNotNull(), reporte(batch, version_juego=None), batch)) == 1


class TestVersionIsAnalyzedBuild:
    def test_dispara_cuando_el_lote_no_declara_build_y_el_reporte_trae_una(self, lote, reporte):
        batch = lote(textos=(BUG_PARED, CITA_V05), build=None)
        hallazgos = correr(VersionIsAnalyzedBuild(), reporte(batch, version_juego="v0.5"), batch)
        assert len(hallazgos) == 1
        assert "la build no fue especificada" in hallazgos[0].message

    def test_dispara_cuando_falta_la_version_y_el_lote_si_declara_build(self, lote, reporte):
        batch = lote()
        hallazgos = correr(VersionIsAnalyzedBuild(), reporte(batch, version_juego=None), batch)
        assert len(hallazgos) == 1
        assert f"la build analizada es '{BUILD}'" in hallazgos[0].message

    def test_dispara_con_una_version_citada_dentro_de_un_comentario(self, lote, reporte):
        """EL EDGE CASE DEL PRODUCTO. Baseline 0/3 -> after 3/3."""
        batch = lote(textos=(BUG_PARED, CITA_V05))
        hallazgos = correr(VersionIsAnalyzedBuild(), reporte(batch, version_juego="v0.5"), batch)
        assert len(hallazgos) == 1
        assert "no es la build analizada" in hallazgos[0].message

    def test_callada_cuando_la_version_es_la_build_analizada(self, lote, reporte):
        batch = lote()
        assert correr(VersionIsAnalyzedBuild(), reporte(batch), batch) == []

    def test_callada_cuando_no_hay_build_y_la_version_es_null(self, lote, reporte):
        """El caso que el baseline marcaba mal. Aqui no se reporta nada."""
        batch = lote(build=None)
        assert correr(VersionIsAnalyzedBuild(), reporte(batch, version_juego=None), batch) == []


# ---------------------------------------------------------------------------
# review.py
# ---------------------------------------------------------------------------


class TestDiscardedBiasRequiresReview:
    def test_dispara_con_un_descarte_por_sesgo_sin_revision(self, lote, reporte):
        batch = lote(textos=(BUG_PARED, BASURA))
        report = reporte(
            batch,
            requiere_revision_humana=False,
            comentarios_descartados=[{"texto": BASURA, "motivo": "extremista"}],
        )
        hallazgos = correr(DiscardedBiasRequiresReview(), report, batch)
        assert len(hallazgos) == 1
        assert hallazgos[0].field == "requiere_revision_humana"

    def test_callada_si_la_revision_ya_esta_marcada(self, lote, reporte):
        batch = lote(textos=(BUG_PARED, BASURA))
        report = reporte(
            batch,
            requiere_revision_humana=True,
            comentarios_descartados=[{"texto": BASURA, "motivo": "extremista"}],
        )
        assert correr(DiscardedBiasRequiresReview(), report, batch) == []

    def test_callada_con_un_descarte_por_ruido(self, lote, reporte):
        """Solo el sesgo y el extremismo la disparan: son juicios sobre el tono.

        En `after`, `AnyDiscardRequiresReview` cubre los demas motivos.
        """
        batch = lote()
        report = reporte(batch, comentarios_descartados=[{"texto": JEFE_FINAL, "motivo": "ruido"}])
        assert correr(DiscardedBiasRequiresReview(), report, batch) == []


class TestMultipleBuildsRequireReview:
    def test_dispara_cuando_el_lote_menciona_dos_builds(self, lote, reporte):
        batch = lote(textos=(BUG_PARED, CITA_V05))  # build v0.8.2 + v0.5 citada
        hallazgos = correr(MultipleBuildsRequireReview(), reporte(batch), batch)
        assert len(hallazgos) == 1
        assert "mas de una version" in hallazgos[0].message

    def test_callada_con_una_sola_build(self, lote, reporte):
        batch = lote()
        assert correr(MultipleBuildsRequireReview(), reporte(batch), batch) == []


class TestAnyDiscardRequiresReview:
    def test_dispara_con_cualquier_descarte_sin_revision(self, lote, reporte):
        batch = lote()
        report = reporte(batch, comentarios_descartados=[{"texto": JEFE_FINAL, "motivo": "ruido"}])
        assert len(correr(AnyDiscardRequiresReview(), report, batch)) == 1

    def test_callada_sin_descartes(self, lote, reporte):
        batch = lote()
        assert correr(AnyDiscardRequiresReview(), reporte(batch), batch) == []

import dataclasses
from collections import Counter
import json
from pathlib import Path
import statistics
import unittest
from unittest.mock import patch

from app.captions.segment_manager import SegmentConfig, SegmentManager, timestamp
from app.captions.transcript_state import TranscriptState


def line(text, start="0:00:02.58", end="0:00:05.80", speaker=1):
    return dict(text=text, start=start, end=end, speaker=speaker)


class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.manager = SegmentManager(session_id="test")
        self.state = TranscriptState()

    def update(self, lines, now):
        self.state.update(dict(lines=lines, buffer_transcription=""))
        return self.manager.update(self.state, now)

    def test_growing_fragment_is_one_sentence(self):
        for now, text in [(0, "La hipertensión arter"), (.3, "La hipertensión arterial es una condición"),
                          (.6, "La hipertensión arterial es una condición cardiovascular.")]:
            result = self.update([line(text)], now)
            self.assertFalse(result.ready_segments)
        result = self.manager.tick(1.6)
        self.assertEqual([s.text for s in result.ready_segments], [text])
        self.assertEqual(result.pending_segment, "")

    def test_last_line_revision_replaces_pending(self):
        self.update([line("Tiene hipotensión.")], 0)
        self.update([line("Tiene hipertensión.")], .7)
        self.assertFalse(self.manager.tick(1).ready_segments)
        segment = self.manager.tick(1.7).ready_segments[0]
        self.assertEqual(segment.text, "Tiene hipertensión.")
        self.assertEqual(segment.revisions_before_ready, 1)

    def test_multiple_lines_and_strong_punctuation(self):
        self.update([line("Primera."), line("¿Segunda? ¡Sí!", "0:00:06.00", "0:00:08.00")], 0)
        result = self.manager.tick(1)
        self.assertEqual([s.text for s in result.ready_segments], ["Primera.", "¿Segunda?", "¡Sí!"])
        self.assertTrue(all(s.reason == "punctuation" for s in result.ready_segments))

    def test_repeated_snapshots_do_not_reset_stability_or_duplicate(self):
        rows = [line("Hola.")]
        self.update(rows, 0)
        self.assertEqual(len(self.update(rows, .8).ready_segments), 1)
        self.assertFalse(self.update(rows, 1).ready_segments)
        self.assertFalse(self.update(rows, 2).ready_segments)
        self.assertFalse(self.manager.finish(3).ready_segments)

    def test_suffix_extension_after_emission(self):
        self.update([line("Primera.")], 0)
        self.manager.tick(1)
        result = self.update([line("Primera. Segunda.", end="0:00:07.00")], 1.1)
        self.assertEqual(result.pending_segment, "Segunda.")
        self.assertEqual(self.manager.tick(2.1).ready_segments[0].text, "Segunda.")

    def test_explicit_silence(self):
        self.update([line("Este contenido tiene seis palabras sin punto"),
                     line("", "0:00:05.80", "0:00:07.00", -2)], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].reason, "silence")
        self.assertEqual(result.ready_segments[0].text, "Este contenido tiene seis palabras sin punto")

    def test_gap_between_lines_flushes_previous_only(self):
        self.update([line("Esta primera unidad contiene seis palabras útiles"),
                     line("Segunda", "0:00:07.20", "0:00:08.00")], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].text, "Esta primera unidad contiene seis palabras útiles")
        self.assertEqual(result.pending_segment, "Segunda")

    def test_no_silence_inferred_from_network_idle(self):
        self.update([line("cardio")], 0)
        segment = self.manager.tick(100).ready_segments[0]
        self.assertEqual(segment.reason, "hard_max_age")

    def test_soft_max_age_waits_for_minimum_and_natural_boundary(self):
        self.manager = SegmentManager(SegmentConfig(
            minimum_words=3, soft_max_age_seconds=3, hard_max_age_seconds=7))
        self.update([line("La condición clínica, cardio")], 0)
        result = self.manager.tick(3)
        self.assertEqual(result.ready_segments[0].text, "La condición clínica,")
        self.assertEqual(result.ready_segments[0].reason, "soft_max_age")
        self.assertEqual(result.pending_segment, "cardio")
        self.update([line("La condición clínica, cardiovascular")], 3.1)
        self.assertEqual(self.manager.finish(3.2).ready_segments[0].text, "cardiovascular")

    def test_soft_max_age_without_natural_boundary_waits_for_hard_limit(self):
        self.update([line("uno dos tres cuatro cinco seis siete")], 0)
        self.assertFalse(self.manager.tick(4.6).ready_segments)
        self.assertEqual(self.manager.tick(7).ready_segments[0].reason, "hard_max_age")

    def test_max_words_whitespace(self):
        self.manager = SegmentManager(SegmentConfig(minimum_words=2, target_words=3, max_words=5))
        result = self.update([line("uno dos tres cuatro cinco")], 0)
        self.assertEqual(result.ready_segments[0].text, "uno dos tres")
        self.assertEqual(result.ready_segments[0].reason, "max_words")
        self.assertEqual(result.pending_segment, "cuatro cinco")

    def test_forced_cut_prefers_comma_or_semicolon(self):
        self.manager = SegmentManager(SegmentConfig(minimum_words=2, target_words=4, max_words=5))
        result = self.update([line("uno dos; tres cuatro cinco")], 0)
        self.assertEqual(result.ready_segments[0].text, "uno dos;")

    def test_max_words_is_a_strong_limit(self):
        self.manager = SegmentManager(SegmentConfig(minimum_words=1, target_words=2, max_words=3))
        result = self.update([line("uno dos tres")], 0)
        self.assertEqual(result.ready_segments[0].reason, "max_words")

    def test_long_punctuated_sentence_still_respects_max_words(self):
        self.manager = SegmentManager(SegmentConfig(minimum_words=2, target_words=3, max_words=5))
        result = self.update([line("uno dos tres cuatro cinco seis siete.")], 0)
        self.assertTrue(all(s.word_count <= 5 for s in result.ready_segments))
        self.assertEqual(result.ready_segments[0].reason, "max_words")

    def test_punctuation_extension_does_not_reset_previous_sentence(self):
        self.update([line("Primera.")], 0)
        self.update([line("Primera. Siguiente palabra")], .7)
        self.assertEqual(self.manager.tick(1).ready_segments[0].text, "Primera.")

    def test_session_end_flush_without_stabilization(self):
        self.update([line("últimas palabras")], 0)
        segment = self.manager.finish(.1).ready_segments[0]
        self.assertEqual((segment.text, segment.reason), ("últimas palabras", "session_end"))
        self.assertFalse(self.manager.finish(.2).ready_segments)
        with self.assertRaises(RuntimeError):
            self.update([line("más")], 1)

    def test_reset_clears_all_state(self):
        self.update([line("Hola")], 0)
        self.manager.finish(1)
        self.manager.reset()
        self.assertEqual(self.manager.emitted_segments, ())
        result = self.update([line("Otra sesión")], 0)
        self.assertEqual(result.pending_segment, "Otra sesión")
        self.assertEqual(self.manager.finish(1).ready_segments[0].id, "test:1")

    def test_late_revision_keeps_ready_immutable_and_maps_suffix(self):
        self.update([line("Tiene hipotensión. y continúa")], 0)
        published = self.manager.tick(1).ready_segments[0]
        result = self.update([line("Tiene hipertensión. y continúa")], 1.1)
        self.assertEqual(result.pending_segment, "y continúa")
        late = [e for e in result.events if e["type"] == "late_revision_detected"]
        self.assertEqual(len(late), 1)
        self.assertIn("hipotensión", late[0]["old_text"])
        self.assertIn("hipertensión", late[0]["new_text"])
        self.assertEqual(self.manager.emitted_segments[0], published)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            published.text = "changed"
        self.assertFalse(self.update([line("Tiene hipertensión. y continúa")], 1.2).events)

    def test_late_extension_of_published_word_does_not_emit_suffix(self):
        self.update([line("arter"), line("", "0:00:05.80", "0:00:07.00", -2)], 0)
        self.manager.tick(7)
        result = self.update([line("arterial es importante")], 7.1)
        self.assertTrue(any(e.get("token_extended") for e in result.events))
        self.assertEqual(result.pending_segment.strip(), "es importante")

    def test_retiming_uses_position_and_overlap(self):
        self.update([line("Hola.")], 0)
        published = self.manager.tick(1).ready_segments[0]
        result = self.update([line("Hola.", "0:00:02.60", "0:00:05.90")], 1.1)
        self.assertFalse(result.ready_segments)
        self.assertTrue(any(e.get("retimed") for e in result.events))
        self.assertEqual(self.manager.emitted_segments[0], published)

    def test_missing_timestamps_falls_back_to_position(self):
        self.update([line("hiper", None, None)], 0)
        self.update([line("hipertensión", None, None)], .1)
        segment = self.manager.finish(.2).ready_segments[0]
        self.assertEqual(segment.text, "hipertensión")
        self.assertIsNone(segment.start_time)

    def test_long_technical_word_never_split(self):
        text = "electroencefalográficamente"
        self.update([line(text)], 0)
        segment = self.manager.tick(7).ready_segments[0]
        self.assertEqual(segment.text, text)
        self.assertEqual(segment.reason, "hard_max_age")

    def test_decimal_is_not_sentence_boundary(self):
        self.update([line("Una medida de 3.5 unidades")], 0)
        self.assertFalse(self.manager.tick(1).ready_segments)

    def test_real_fixture_and_timestamps(self):
        path = Path(__file__).parent / "fixtures/wlk_0_2_26_simulstreaming_es_real_voice.json"
        payloads = json.loads(path.read_text(encoding="utf-8"))["payloads"]
        for i, payload in enumerate(payloads):
            self.state.update(payload)
            self.manager.update(self.state, i * .2)
        segment = self.manager.finish(.5).ready_segments[0]
        self.assertEqual(segment.text, payloads[-1]["lines"][0]["text"].strip())
        self.assertEqual((segment.start_time, segment.end_time), (2.58, 5.0))
        self.assertEqual(segment.timing_precision, "source_line_bounds")

    def test_metrics_and_monotonic_clock(self):
        self.update([line("Hola mundo.")], .2)
        s = self.manager.tick(1.2).ready_segments[0]
        self.assertEqual((s.word_count, s.latency_ms, s.first_seen_at), (2, 1000., .2))
        with self.assertRaises(ValueError):
            self.manager.tick(.1)

    def test_invalid_config_and_time(self):
        for kwargs in [dict(max_words=0), dict(stabilization_seconds=-1),
                       dict(tick_seconds=float('nan')),
                       dict(soft_max_age_seconds=8, hard_max_age_seconds=7),
                       dict(minimum_words=17, target_words=16),
                       dict(safe_cut_lookback_words=0)]:
            with self.assertRaises(ValueError):
                SegmentConfig(**kwargs)
        self.assertEqual(timestamp("1:02:03.45"), 3723.45)
        self.assertIsNone(timestamp("bad"))

    def test_config_reads_batching_thresholds_from_environment(self):
        values = {
            "SEGMENT_MINIMUM_WORDS": "7",
            "SEGMENT_TARGET_WORDS": "17",
            "SEGMENT_MAX_WORDS": "25",
            "SEGMENT_SAFE_CUT_LOOKBACK_WORDS": "9",
            "SEGMENT_SOFT_MAX_AGE_SECONDS": "5.5",
            "SEGMENT_HARD_MAX_AGE_SECONDS": "8.0",
        }
        with patch.dict("os.environ", values):
            config = SegmentConfig.from_env()
        self.assertEqual((config.minimum_words, config.target_words, config.max_words),
                         (7, 17, 25))
        self.assertEqual(config.safe_cut_lookback_words, 9)
        self.assertEqual((config.soft_max_age_seconds, config.hard_max_age_seconds),
                         (5.5, 8.0))

    def test_same_spoken_text_at_different_times_is_not_deduplicated(self):
        self.update([line("Sí."), line("Sí.", "0:00:08.00", "0:00:09.00")], 0)
        self.assertEqual([s.text for s in self.manager.tick(1).ready_segments], ["Sí.", "Sí."])

    def test_removed_published_line_reports_once(self):
        self.update([line("Hola.")], 0)
        self.manager.tick(1)
        result = self.update([], 2)
        self.assertTrue(any(e.get("removed") for e in result.events))
        self.assertFalse(self.update([], 3).events)
        self.assertEqual(self.manager.emitted_segments[0].text, "Hola.")

    def test_boundary_crossing_late_revision_quarantines_ambiguous_text(self):
        self.update([line("Viejo. cambia sin publicar")], 0)
        self.manager.tick(1)
        result = self.update([line("Todo revisado sin publicar")], 1.1)
        self.assertTrue(any(e.get("boundary_crossed") for e in result.events))
        self.assertEqual(result.pending_segment.strip(), "sin publicar")
        self.assertEqual(self.manager.emitted_segments[0].text, "Viejo.")

    def test_exact_split_of_fully_published_line_does_not_duplicate(self):
        self.update([line("Primera. Segunda.", end="0:00:08.00")], 0)
        self.assertEqual(len(self.manager.tick(1).ready_segments), 2)
        result = self.update([line("Primera.", end="0:00:05.00"),
                              line("Segunda.", "0:00:05.00", "0:00:08.00")], 1.1)
        self.assertEqual(result.pending_segment, "")
        self.assertTrue(any(e.get("resegmented") for e in result.events))
        self.assertFalse(self.manager.finish(2).ready_segments)

    def test_real_medical_replay_conserves_words_and_ids(self):
        from replay_fixture import replay
        fixture = json.loads((Path(__file__).parents[1] / "benchmarks/medical_real_snapshots.json").read_text(encoding="utf-8"))
        results = list(replay(fixture["events"], self.manager))
        emitted = [s for _, r in results for s in r.ready_segments]
        final_payload = next(e["payload"] for e in reversed(fixture["events"]) if "lines" in e["payload"])
        expected_words = " ".join(l["text"] for l in final_payload["lines"] if l.get("text")).split()
        self.assertEqual(" ".join(s.text for s in emitted).split(), expected_words)
        self.assertEqual([s.text for s in emitted], [
            "La hipertensión arterial es una condición cardiovascular",
            "caracterizada por una elevación persistente de la presión",
            "arterial systólica y/o diastólica.",
            "Suficio patología involucra mecanismos complejos,",
            "incluyendo la activación del sistema herenina angiotensina",
            "al dosterona.",
            "El aumento de la resistencia vascular periférica",
            "y alteraciones en la función endotelial.",
            "En pacientes y pertencios,",
            "la exposición prolongada a niveles elevados de",
            "presión puede producir hipertrofia ventricular",
            "izquierda,",
            "remodelado vascular,",
            "disfunción renal y un incremento significativo del",
            "riesgo de accidentes cerebrovascular e infarto agudo de",
            "miocardio.",
        ])
        self.assertEqual(Counter(s.reason for s in emitted),
                         Counter(soft_max_age=10, punctuation=3,
                                 hard_max_age=2, session_end=1))
        self.assertEqual([s.word_count for s in emitted],
                         [7, 8, 4, 5, 7, 2, 7, 6, 4, 7, 5, 1, 2, 7, 8, 1])
        self.assertEqual(sum(s.boundary_kind == "whitespace"
                             and s.reason in {"soft_max_age", "hard_max_age", "max_words"}
                             for s in emitted), 8)
        self.assertEqual(Counter(s.boundary_kind for s in emitted),
                         Counter(whitespace=8, comma=4,
                                 strong_punctuation=3, session_end=1))
        latencies = [s.latency_ms for s in emitted]
        self.assertLessEqual(statistics.median(latencies), 4500)
        self.assertLessEqual(max(latencies), 5600)
        self.assertEqual(len({s.id for s in emitted}), len(emitted))
        self.assertEqual(results[-1][1].pending_segment, "")
        self.assertTrue(all(s.text and s.word_count > 0 for s in emitted))
        self.assertFalse([e for _,r in results for e in r.events if e["type"] == "late_revision_detected"])

    def test_soft_age_does_not_emit_tiny_fragment(self):
        self.update([line("solo dos")], 0)
        self.assertFalse(self.manager.tick(4.6).ready_segments)
        result = self.manager.tick(7.1)
        self.assertEqual([s.text for s in result.ready_segments], ["solo", "dos"])
        self.assertTrue(all(s.reason == "hard_max_age" for s in result.ready_segments))
        self.assertEqual(result.pending_segment, "")

    def test_hard_age_flushes_single_open_word(self):
        self.update([line("cardio")], 0)
        self.assertFalse(self.manager.tick(5.4).ready_segments)
        segment = self.manager.tick(5.5).ready_segments[0]
        self.assertEqual((segment.text, segment.reason), ("cardio", "hard_max_age"))

    def test_hard_age_keeps_open_terminal_word_when_complete_words_exist(self):
        self.update([line("uno dos")], 0)
        self.update([line("uno dos cardio")], 5.0)
        result = self.manager.tick(5.5)
        self.assertEqual(result.ready_segments[0].text, "uno dos")
        self.assertEqual(result.pending_segment, "cardio")
        result = self.update([line("uno dos cardiovascular")], 5.6)
        self.assertFalse([e for e in result.events if e["type"] == "late_revision_detected"])
        self.assertEqual(self.manager.finish(5.7).ready_segments[0].text, "cardiovascular")

    def test_safe_cut_prefers_line_boundary_over_whitespace(self):
        self.manager = SegmentManager(SegmentConfig(
            minimum_words=2, target_words=4, max_words=5,
            safe_cut_lookback_words=4))
        result = self.update([
            line("uno dos", end="0:00:05.80"),
            line("tres cuatro cinco", "0:00:05.80", "0:00:08.00"),
        ], 0)
        segment = result.ready_segments[0]
        self.assertEqual((segment.text, segment.boundary_kind), ("uno dos", "line"))
        self.assertEqual(result.pending_segment, "tres cuatro cinco")

    def test_safe_cut_lookback_ignores_distant_punctuation(self):
        self.manager = SegmentManager(SegmentConfig(
            minimum_words=2, target_words=10, max_words=10,
            safe_cut_lookback_words=3))
        result = self.update([line("uno dos tres, cuatro cinco seis siete ocho nueve diez")], 0)
        segment = result.ready_segments[0]
        self.assertEqual(segment.word_count, 9)
        self.assertEqual(segment.boundary_kind, "whitespace")

    def test_safe_cut_prefers_semicolon_over_later_comma(self):
        self.manager = SegmentManager(SegmentConfig(
            minimum_words=2, target_words=6, max_words=7,
            safe_cut_lookback_words=6))
        result = self.update([line("uno dos; tres cuatro, cinco seis siete")], 0)
        segment = result.ready_segments[0]
        self.assertEqual((segment.text, segment.boundary_kind), ("uno dos;", "semicolon"))
        self.assertEqual(result.pending_segment, "tres cuatro, cinco seis siete")

    def test_target_words_uses_natural_boundary(self):
        text = "uno dos tres cuatro cinco seis, siete ocho nueve diez once doce trece catorce quince dieciséis"
        self.update([line(text)], 0)
        segment = self.manager.tick(.8).ready_segments[0]
        self.assertEqual(segment.text, "uno dos tres cuatro cinco seis,")
        self.assertEqual(segment.reason, "target_words")

    def test_silence_requires_linguistically_useful_content(self):
        rows = [line("muy corto"), line("", "0:00:05.80", "0:00:07.00", -2)]
        self.update(rows, 0)
        self.assertFalse(self.manager.tick(1).ready_segments)
        self.assertEqual(self.manager.tick(7).ready_segments[0].reason, "hard_max_age")


if __name__ == "__main__":
    unittest.main()

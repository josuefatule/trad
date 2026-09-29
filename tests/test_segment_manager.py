import dataclasses
import json
from pathlib import Path
import unittest

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
        self.update(rows, .8)
        self.assertEqual(len(self.update(rows, 1).ready_segments), 1)
        self.assertFalse(self.update(rows, 2).ready_segments)
        self.assertFalse(self.manager.finish(3).ready_segments)

    def test_suffix_extension_after_emission(self):
        self.update([line("Primera.")], 0)
        self.manager.tick(1)
        result = self.update([line("Primera. Segunda.", end="0:00:07.00")], 1.1)
        self.assertEqual(result.pending_segment, "Segunda.")
        self.assertEqual(self.manager.tick(2.1).ready_segments[0].text, "Segunda.")

    def test_explicit_silence(self):
        self.update([line("Sin punto"), line("", "0:00:05.80", "0:00:07.00", -2)], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].reason, "silence")
        self.assertEqual(result.ready_segments[0].text, "Sin punto")

    def test_gap_between_lines_flushes_previous_only(self):
        self.update([line("Primera"), line("Segunda", "0:00:07.20", "0:00:08.00")], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].text, "Primera")
        self.assertEqual(result.pending_segment, "Segunda")

    def test_no_silence_inferred_from_network_idle(self):
        self.update([line("cardio")], 0)
        self.assertFalse(self.manager.tick(100).ready_segments)

    def test_max_age_leaves_terminal_fragment(self):
        self.update([line("La condición cardio")], 0)
        result = self.manager.tick(3)
        self.assertEqual(result.ready_segments[0].text, "La condición")
        self.assertEqual(result.ready_segments[0].reason, "max_age")
        self.assertEqual(result.pending_segment, "cardio")
        self.update([line("La condición cardiovascular")], 3.1)
        self.assertEqual(self.manager.finish(3.2).ready_segments[0].text, "cardiovascular")

    def test_max_words_whitespace(self):
        self.manager = SegmentManager(SegmentConfig(target_words=3, max_words=5))
        self.update([line("uno dos tres cuatro cinco")], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].text, "uno dos tres")
        self.assertEqual(result.ready_segments[0].reason, "max_words")
        self.assertEqual(result.pending_segment, "cuatro cinco")

    def test_forced_cut_prefers_comma_or_semicolon(self):
        self.manager = SegmentManager(SegmentConfig(target_words=4, max_words=5))
        self.update([line("uno dos; tres cuatro cinco")], 0)
        result = self.manager.tick(1)
        self.assertEqual(result.ready_segments[0].text, "uno dos;")

    def test_max_words_waits_for_stability(self):
        self.manager = SegmentManager(SegmentConfig(target_words=2, max_words=3))
        self.assertFalse(self.update([line("uno dos tres")], 0).ready_segments)
        self.assertFalse(self.manager.tick(.5).ready_segments)

    def test_long_punctuated_sentence_still_respects_max_words(self):
        self.manager = SegmentManager(SegmentConfig(target_words=3, max_words=5))
        self.update([line("uno dos tres cuatro cinco seis siete.")], 0)
        result = self.manager.tick(1)
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
        self.manager.tick(1)
        result = self.update([line("arterial es importante")], 1.1)
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
        self.assertFalse(self.manager.tick(20).ready_segments)
        self.assertEqual(self.manager.finish(21).ready_segments[0].text, text)

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
        for kwargs in [dict(max_words=0), dict(stabilization_seconds=-1), dict(tick_seconds=float('nan'))]:
            with self.assertRaises(ValueError):
                SegmentConfig(**kwargs)
        self.assertEqual(timestamp("1:02:03.45"), 3723.45)
        self.assertIsNone(timestamp("bad"))

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
        self.assertEqual(len({s.id for s in emitted}), len(emitted))
        self.assertEqual(results[-1][1].pending_segment, "")
        self.assertTrue(all(s.text and s.word_count > 0 for s in emitted))
        self.assertFalse([e for _,r in results for e in r.events if e["type"] == "late_revision_detected"])


if __name__ == "__main__":
    unittest.main()

import unittest

from app.captions.transcript_state import TranscriptState


def line(text, start="0:00:00.00", end="0:00:01.20", speaker=1):
    return {"speaker": speaker, "text": text, "start": start, "end": end}


def snapshot(lines=None, partial="", diarization=""):
    # Shape from installed FrontData.to_dict(), not invented delta messages.
    return {"status": "active_transcription", "lines": lines or [],
            "buffer_transcription": partial, "buffer_diarization": diarization,
            "buffer_translation": "", "remaining_time_transcription": 0.,
            "remaining_time_transcription_processing": 0.,
            "remaining_time_transcription_policy": 0., "remaining_time_diarization": 0.}


class TranscriptTests(unittest.TestCase):
    def setUp(self):
        self.state = TranscriptState()

    def test_partial_replaced(self):
        self.state.update(snapshot(partial="La hipertensión"))
        self.state.update(snapshot(partial="La hipertensión arterial"))
        self.assertEqual(self.state.partial_text, "La hipertensión arterial")
        self.assertEqual(self.state.confirmed_text, "")

    def test_confirmation(self):
        self.state.update(snapshot(partial="La hipertensión"))
        self.state.update(snapshot([line("La hipertensión")], "arterial"))
        self.assertEqual(self.state.confirmed_text, "La hipertensión")
        self.assertEqual(self.state.partial_text, "arterial")

    def test_growing_line_and_repeated_snapshot(self):
        for text in ["La hipertensión", "La hipertensión arterial", "La hipertensión arterial es"]:
            self.state.update(snapshot([line(text)]))
        self.assertFalse(self.state.update(snapshot([line("La hipertensión arterial es")])))
        self.assertEqual(self.state.confirmed_text, "La hipertensión arterial es")

    def test_multiple_sentences_silence_and_timestamps(self):
        lines = [line("Primera frase."), line("", speaker=-2),
                 line("Segunda frase.", "0:00:03.00", "0:00:04.25")]
        self.state.update(snapshot(lines))
        self.assertEqual(self.state.confirmed_text, "Primera frase. Segunda frase.")
        self.assertEqual(self.state.segments, lines)

    def test_actual_repeated_speech_is_preserved(self):
        self.state.update(snapshot([line("Sí."), line("Sí.", "0:00:02.00")]))
        self.assertEqual(self.state.confirmed_text, "Sí. Sí.")

    def test_reset(self):
        self.state.update(snapshot([line("Hola")], "mundo"))
        self.state.reset()
        self.assertEqual(self.state.to_dict(), TranscriptState().to_dict())

    def test_control_messages_do_not_promote_partial(self):
        self.state.update(snapshot(partial="inestable"))
        self.state.update({"type": "ready_to_stop"})
        self.assertEqual(self.state.confirmed_text, "")
        self.assertEqual(self.state.partial_text, "inestable")

    def test_pending_diarization_moves_without_duplication(self):
        self.state.update(snapshot(diarization="Hola"))
        self.assertEqual(self.state.confirmed_text, "Hola")
        self.state.update(snapshot([line("Hola")]))
        self.assertEqual(self.state.confirmed_text, "Hola")

    def test_snapshots_are_not_aliased(self):
        payload = snapshot([line("Hola")])
        self.state.update(payload)
        payload["lines"][0]["text"] = "changed"
        self.assertEqual(self.state.segments[0]["text"], "Hola")


if __name__ == "__main__":
    unittest.main()

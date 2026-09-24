"""WLK full-mode snapshots, never an append-only stream of hypotheses."""
from copy import deepcopy


class TranscriptState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.partial_text = ""
        self.confirmed_text = ""
        self.segments = []
        self.pending_diarization_text = ""

    def update(self, payload: dict) -> bool:
        # Control messages (config/ready_to_stop/errors) aren't snapshots.
        if "lines" not in payload:
            return False
        lines = payload["lines"]
        if not isinstance(lines, list) or any(not isinstance(x, dict) for x in lines):
            raise ValueError("Invalid WLK full snapshot: lines must be objects")
        previous = self.to_dict()
        self.segments = deepcopy(lines)
        self.partial_text = payload.get("buffer_transcription", "") or ""
        # These tokens are committed by ASR but await speaker attribution.
        self.pending_diarization_text = payload.get("buffer_diarization", "") or ""
        speech = [x.get("text") or "" for x in lines if x.get("speaker") != -2]
        self.confirmed_text = " ".join(
            text.strip() for text in [*speech, self.pending_diarization_text] if text.strip()
        )
        return previous != self.to_dict()

    def to_dict(self):
        return {
            "partial_text": self.partial_text,
            "confirmed_text": self.confirmed_text,
            "segments": deepcopy(self.segments),
            "pending_diarization_text": self.pending_diarization_text,
        }

"""Persisted overlay appearance, independent of audio/session configuration."""
import json
from pathlib import Path
import re


class OverlayStyleStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else Path(__file__).resolve().parents[2] / ".runtime" / "overlay-style.json"
        self.text_color = "#ffffff"
        self.background_color = "#001264"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            text_color = self.validate(data["text_color"])
            background_color = self.validate(data.get("background_color", "#001264"))
            self.text_color, self.background_color = text_color, background_color
        except (OSError, ValueError, KeyError, TypeError):
            pass

    @staticmethod
    def validate(value):
        if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("Expected a six-digit hexadecimal color")
        return value.lower()

    def to_dict(self):
        return {"text_color": self.text_color, "background_color": self.background_color}

    def save(self, color=None, background_color=None):
        color = self.text_color if color is None else self.validate(color)
        background_color = self.background_color if background_color is None else self.validate(background_color)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"text_color": color, "background_color": background_color}), encoding="utf-8")
        temporary.replace(self.path)
        self.text_color = color
        self.background_color = background_color
        return self.to_dict()

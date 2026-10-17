from dataclasses import asdict, dataclass, replace
import math
import os


@dataclass(frozen=True)
class CaptionConfig:
    max_lines: int = 2
    font_size: int = 48
    max_width: int = 1500
    position: str = "bottom"
    bottom_offset: int = 70
    background_opacity: float = .72
    min_display_ms: int = 1800
    max_display_ms: int = 6500
    reading_wps: float = 3.
    visual_queue_max: int = 64
    max_backlog_ms: int = 20000

    def __post_init__(self):
        limits = {"max_lines": (1, 4), "font_size": (16, 96),
                  "max_width": (240, 3840), "bottom_offset": (0, 1000),
                  "background_opacity": (0, 1), "min_display_ms": (300, 10000),
                  "max_display_ms": (500, 30000), "reading_wps": (1, 8),
                  "visual_queue_max": (1, 256), "max_backlog_ms": (1000, 120000)}
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid caption setting: {name}")
        if self.position not in {"bottom", "top", "center"}:
            raise ValueError("Invalid caption position")
        if self.min_display_ms > self.max_display_ms:
            raise ValueError("Caption minimum display time exceeds maximum")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(**{name: type(getattr(defaults, name))(
            os.getenv("CAPTION_" + name.upper(), getattr(defaults, name)))
            for name in asdict(defaults)})

    def with_query(self, query):
        # Only these names and validated numeric/enum values reach the renderer.
        allowed = {key: type(value) for key, value in asdict(self).items()
                   if key != "visual_queue_max"}
        if any(key not in allowed for key in query):
            raise ValueError("Unknown overlay parameter")
        return replace(self, **{key: allowed[key](value) for key, value in query.items()})

    def to_dict(self):
        return asdict(self)

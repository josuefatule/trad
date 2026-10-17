from dataclasses import asdict, dataclass, replace
import math
import os


@dataclass(frozen=True)
class CaptionConfig:
    mode: str = "persistent_rolling"
    max_lines: int = 3
    stop_clear_ms: int = 8000
    font_size: int = 48
    max_width: int = 1500
    canvas_width: int = 1920
    canvas_height: int = 1080
    region_x: int = 0
    region_y: int = 930
    region_width: int = 1920
    region_height: int = 150
    padding_x: int = 32
    padding_y: int = 8
    line_height: float = 1.2
    position: str = "center"
    bottom_offset: int = 70
    background_opacity: float = 0.
    min_display_ms: int = 1800
    max_display_ms: int = 6500
    reading_wps: float = 3.
    visual_queue_max: int = 64
    max_backlog_ms: int = 20000
    reconnect_attempts: int = 8
    reconnect_base_ms: int = 500
    reconnect_max_ms: int = 10000

    def __post_init__(self):
        limits = {"max_lines": (1, 3), "stop_clear_ms": (0, 120000), "font_size": (16, 96),
                  "max_width": (240, 3840), "bottom_offset": (0, 1000),
                  "background_opacity": (0, 1), "min_display_ms": (300, 10000),
                  "max_display_ms": (500, 30000), "reading_wps": (1, 8),
                  "visual_queue_max": (1, 256), "max_backlog_ms": (1000, 120000),
                  "canvas_width": (240, 7680), "canvas_height": (150, 4320),
                  "region_x": (0, 7680), "region_y": (0, 4320),
                  "region_width": (80, 7680), "region_height": (40, 4320),
                  "padding_x": (8, 200), "padding_y": (8, 200),
                  "line_height": (1.1, 1.6), "reconnect_attempts": (1,20),
                  "reconnect_base_ms": (100,5000), "reconnect_max_ms": (500,30000)}
        for name, (low, high) in limits.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid caption setting: {name}")
        if self.position not in {"bottom", "top", "center"}:
            raise ValueError("Invalid caption position")
        if self.mode not in {"persistent_rolling", "timed_queue"}:
            raise ValueError("Invalid caption mode")
        if self.min_display_ms > self.max_display_ms:
            raise ValueError("Caption minimum display time exceeds maximum")
        if self.reconnect_base_ms>self.reconnect_max_ms:raise ValueError("Invalid reconnect interval")
        if (self.region_x + self.region_width > self.canvas_width or
                self.region_y + self.region_height > self.canvas_height):
            raise ValueError("Caption region exceeds canvas")
        if self.region_width - 2 * self.padding_x < 40:
            raise ValueError("Caption region has insufficient text width")
        if self.region_height - 2 * self.padding_y < self.font_size * self.line_height:
            raise ValueError("Caption region cannot fit one line at configured font size")

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

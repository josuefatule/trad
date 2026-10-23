"""The two explicit, immutable conference directions; no language detection."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SessionDirection:
    id: str
    source_language: str
    target_language: str
    normalization_mode: str

    def to_dict(self):
        return asdict(self)


DIRECTIONS = {
    "en-es": SessionDirection("en-es", "en", "es", "identity"),
    "es-en": SessionDirection("es-en", "es", "en", "spanish_glossary"),
}
DEFAULT_DIRECTION = "en-es"


def direction_from_id(value):
    if not isinstance(value, str) or value not in DIRECTIONS:
        raise ValueError("Direction must be en-es or es-en")
    return DIRECTIONS[value]

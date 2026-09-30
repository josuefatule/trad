"""Provider-agnostic, ordered translation for immutable caption segments."""

from .engine import TranslationConfig, TranslationEngine, build_translation_engine
from .models import TranslationContextSegment, TranslationRequest, TranslationResult
from .providers import DeepLTranslatorProvider, MockTranslatorProvider, TranslatorProvider

__all__ = (
    "DeepLTranslatorProvider",
    "MockTranslatorProvider",
    "TranslationConfig",
    "TranslationContextSegment",
    "TranslationEngine",
    "TranslationRequest",
    "TranslationResult",
    "TranslatorProvider",
    "build_translation_engine",
)

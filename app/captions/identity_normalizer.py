"""Preserve English exactly until an English glossary has been validated."""
from .terminology_normalizer import NormalizedSegment


class IdentityNormalizer:
    def normalize(self, segment_id, raw_text):
        return NormalizedSegment(segment_id, raw_text, raw_text, (), (), (), 0.)

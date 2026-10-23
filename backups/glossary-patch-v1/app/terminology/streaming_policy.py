"""Opt-in medical boundaries and unambiguous pressure-token joins.

The original segment manager and glossary remain unchanged. A bounded grace
period protects unfinished expressions without retaining speech indefinitely.
"""
import re

from app.captions.segment_manager import SegmentManager
from app.captions.terminology_normalizer import Correction, _case_like, _source_tokens

POLICY_VERSION = 'medical-streaming-v2'
PRESSURE_SPLITS = re.compile(r"(?<![\w'’\-])(?:hyper|hypo)[ \t]+tension(?![\w'’])", re.I)
TRAILING_CONNECTORS = frozenset(
    'a an the and or by of in to with without no not is are was were has have '
    'will should must there this these those el la los las un una y o de del en con sin no'.split()
)
EXTRA_PHRASES = {
    'en': ('hyper tension', 'hypo tension', 'orthostatic hypotension',
           'physical inactivity', 'shortness of breath', 'mm of mercury',
           'millimeters of mercury', 'millimetres of mercury',
           # Preserve this observed ASR surface as a whole without translating
           # or reclassifying it as either systolic or diastolic.
           'the astolic blood pressure'),
    'es': ('falta de aire', 'dificultad para respirar', 'milímetros de mercurio'),
}


def pressure_split_corrections(text):
    """Join only explicit HYPER/HYPO + tension; never infer a direction."""
    return [Correction(m.group(), _case_like(m.group(), re.sub(r'[ \t]+', '', m.group()).lower()),
                       m.start(), m.end(), 'medical_token_join', 1.0,
                       re.sub(r'[ \t]+', '', m.group()).lower())
            for m in PRESSURE_SPLITS.finditer(text)
            if not any('_' in word for word in re.split(r'[,;:.!?\n]',text[:m.start()])[-1].split()[-3:])]


class MedicalBoundaries:
    def __init__(self, release, language):
        phrases = [c[language] for c in release.concepts]
        phrases += [f['form'] for f in release.forms
                    if f['language'] == language and f['bucket'] == 'reviewable_variant']
        phrases += list(EXTRA_PHRASES.get(language, ()))
        self.prefixes = set()
        self.phrases = set()
        self.max_length = 1
        for phrase in phrases:
            words = tuple(t.normalized for t in _source_tokens(phrase))
            if len(words) < 2:
                continue
            self.phrases.add(words)
            self.prefixes.update(words[:i] for i in range(1, len(words)))
            self.max_length = max(self.max_length, len(words))
        self._text = None

    def _analyse(self, text):
        if text == self._text:
            return
        self._text = text
        self._tokens = _source_tokens(text)
        words = tuple(t.normalized for t in self._tokens)
        self._spans = []
        for start in range(len(words)):
            for end in range(start + 2, min(len(words), start + self.max_length) + 1):
                if words[start:end] in self.phrases:
                    # A punctuation break is not a medical multiword span.
                    gap = text[self._tokens[start].start:self._tokens[end - 1].end]
                    if not re.search(r'[,;.!?]', gap):
                        self._spans.append((self._tokens[start].start, self._tokens[end - 1].end))

    def allowed(self, text, cut):
        self._analyse(text)
        if any(start < cut < end for start, end in self._spans):
            return False
        left = text[:cut].rstrip()
        if re.search(r'[.!?,;:]$', left):
            return True
        tokens = [t for t in self._tokens if t.end <= cut]
        if not tokens:
            return False
        if tokens[-1].normalized in TRAILING_CONNECTORS:
            return False
        # A complete expression may also be a prefix of a longer expression.
        # It can stand alone when its continuation has not arrived yet.
        if any(end == tokens[-1].end for _, end in self._spans):
            return True
        words = tuple(t.normalized for t in tokens)
        return not any(words[-width:] in self.prefixes
                       for width in range(1, min(len(words), self.max_length - 1) + 1))


class MedicalSegmentManager(SegmentManager):
    """Same original defaults; medical cuts are enabled only in soft mode."""
    grace_seconds = 1.5

    def __init__(self, config=None, session_id='session', *, boundaries):
        self.boundaries = boundaries
        super().__init__(config, session_id)

    def _safe_cut(self, text, refs, line_cuts, now, *, allow_whitespace,
                  minimum_whitespace_words=1, require_stability=True):
        words = list(re.finditer(r'\S+', text))
        complete = [w for w in words if w.end() < len(text) and text[w.end()].isspace()]
        anchor = min(len(complete), self.config.target_words)
        lower = max(1, anchor - self.config.safe_cut_lookback_words + 1)
        candidates = []
        for number in range(lower, anchor + 1):
            token = complete[number - 1]
            cut = token.end()
            if require_stability and not self._stable(refs, cut, now):
                continue
            if not self.boundaries.allowed(text, cut):
                continue
            if re.search(r'[.!?]+$', token.group()):
                priority, kind = 0, 'strong_punctuation'
            elif token.group().endswith(';'):
                priority, kind = 1, 'semicolon'
            elif token.group().endswith(','):
                priority, kind = 2, 'comma'
            elif cut in line_cuts:
                priority, kind = 3, 'line'
            elif allow_whitespace and number >= minimum_whitespace_words:
                priority, kind = 4, 'whitespace'
            else:
                continue
            minimum_unit = (min(self.config.minimum_words,minimum_whitespace_words)
                            if allow_whitespace else self.config.minimum_words)
            if kind == 'whitespace':
                minimum_unit = max(minimum_unit,self.config.minimum_words)
            if kind != 'strong_punctuation' and number < minimum_unit:
                continue
            candidates.append((priority, -number, cut, kind))
        if not candidates:
            return 0, None
        _, _, cut, kind = min(candidates)
        return cut, kind

    def _choose(self, text, refs, pauses, line_cuts, now):
        result = super()._choose(text, refs, pauses, line_cuts, now)
        cut, reason, kind = result
        terminal_fallback_unstable = (cut == len(text) and reason == 'hard_max_age'
                                      and not self._stable(refs,cut,now))
        if cut and not terminal_fallback_unstable and self.boundaries.allowed(text, cut):
            return result
        # Prefer a safe complete expression beyond the usual target, still
        # inside the original maximum. This also handles a long first term.
        if len(text.split()) >= self.config.max_words:
            words = list(re.finditer(r'\S+', text))
            for number in range(min(len(words), self.config.max_words), 0, -1):
                end = words[number - 1].end()
                if end < len(text) and self.boundaries.allowed(text, end):
                    return end, 'max_words', 'medical_boundary'
            # Keep the resource bound even for pathological compound input.
            fallback, boundary = super()._safe_cut(text, refs, line_cuts, now,
                allow_whitespace=True, require_stability=False)
            if fallback:
                self._event('medical_boundary_bypass', reason='word_limit')
                return fallback, 'max_words', boundary
        if cut:
            first = min(s.first_seen[i] for r in refs if r is not None for s, i in [r])
            if now - first >= self.config.hard_max_age_seconds + self.grace_seconds:
                self._event('medical_boundary_bypass', reason='bounded_wait_expired')
                return result
        return 0, None, None


def session_segment_manager(normalizer, config, session_id):
    if getattr(normalizer, 'mode', None) == 'soft':
        return MedicalSegmentManager(config, session_id,
            boundaries=MedicalBoundaries(normalizer.release, normalizer.language))
    return SegmentManager(config, session_id)

"""Conservative, deterministic terminology normalization for immutable READY text."""
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
import math
import os
from pathlib import Path
import re
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
WORD_RE = re.compile(r"[^\W_]+(?:[’'][^\W_]+)*", re.UNICODE)
SAFE_JOIN_RE = re.compile(r"^[\s\-‐‑–—]*$")
POLICIES = {"exact", "fuzzy", "suggest"}


@dataclass(frozen=True)
class NormalizerConfig:
    auto_threshold: float = .96
    suggest_threshold: float = .86
    max_token_delta: int = 1
    context_words: int = 8
    collapsed_min_characters: int = 10
    collapsed_max_edits: int = 1
    medical_glossary: str = str(ROOT / "glossaries" / "medical_base.json")
    conference_glossary: str = str(ROOT / "glossaries" / "conference.json")

    def __post_init__(self):
        for name in ("auto_threshold", "suggest_threshold"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.auto_threshold <= self.suggest_threshold:
            raise ValueError("auto_threshold must exceed suggest_threshold")
        if (self.max_token_delta < 0 or self.context_words < 1
                or self.collapsed_min_characters < 1 or self.collapsed_max_edits < 0):
            raise ValueError("token/edit limits must be non-negative and context sizes positive")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            auto_threshold=float(os.getenv("NORMALIZER_AUTO_THRESHOLD", defaults.auto_threshold)),
            suggest_threshold=float(os.getenv("NORMALIZER_SUGGEST_THRESHOLD", defaults.suggest_threshold)),
            max_token_delta=int(os.getenv("NORMALIZER_MAX_TOKEN_DELTA", defaults.max_token_delta)),
            context_words=int(os.getenv("NORMALIZER_CONTEXT_WORDS", defaults.context_words)),
            collapsed_min_characters=int(os.getenv(
                "NORMALIZER_COLLAPSED_MIN_CHARACTERS", defaults.collapsed_min_characters)),
            collapsed_max_edits=int(os.getenv(
                "NORMALIZER_COLLAPSED_MAX_EDITS", defaults.collapsed_max_edits)),
            medical_glossary=os.getenv("NORMALIZER_MEDICAL_GLOSSARY", defaults.medical_glossary),
            conference_glossary=os.getenv("NORMALIZER_CONFERENCE_GLOSSARY", defaults.conference_glossary),
        )


@dataclass(frozen=True)
class Correction:
    source: str
    replacement: str
    start: int
    end: int
    rule: str
    confidence: float
    canonical: str | None


@dataclass(frozen=True)
class Suggestion:
    source: str
    candidate: str
    start: int | None
    end: int | None
    rule: str
    confidence: float
    cross_segment: bool = False
    previous_segment_id: str | None = None


@dataclass(frozen=True)
class NormalizedSegment:
    segment_id: str
    raw_text: str
    normalized_text: str
    corrections: tuple[Correction, ...]
    suggestions: tuple[Suggestion, ...]
    known_terms: tuple[str, ...]
    processing_ms: float

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class _Term:
    canonical: str
    canonical_tokens: tuple[str, ...]
    variants: tuple[str, ...]
    aliases: tuple[str, ...]
    policy: str
    auto_threshold: float
    suggest_threshold: float
    order: int


@dataclass(frozen=True)
class _Token:
    text: str
    normalized: str
    start: int
    end: int


@dataclass(frozen=True)
class _Match:
    start_token: int
    end_token: int
    start: int
    end: int
    term: _Term
    confidence: float
    rule: str
    action: str


def _fold(value):
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _tokens(value):
    return tuple(_fold(match.group()) for match in WORD_RE.finditer(value))


def _source_tokens(value):
    return tuple(_Token(match.group(), _fold(match.group()), match.start(), match.end())
                 for match in WORD_RE.finditer(value))


def _valid_span(text, tokens, start, end):
    return all(SAFE_JOIN_RE.fullmatch(text[tokens[index].end:tokens[index + 1].start])
               for index in range(start, end - 1))


def _case_like(source, canonical):
    letters = "".join(char for char in source if char.isalpha())
    if letters and letters.isupper():
        return canonical.upper()
    first = next((char for char in source if char.isalpha()), "")
    if first.isupper():
        return canonical[:1].upper() + canonical[1:]
    return canonical


def _score(source_tokens, canonical_tokens):
    source = " ".join(source_tokens)
    canonical = " ".join(canonical_tokens)
    spaced = SequenceMatcher(None, source, canonical).ratio()
    compact = SequenceMatcher(None, source.replace(" ", ""),
                              canonical.replace(" ", "")).ratio()
    count = min(len(source_tokens), len(canonical_tokens)) / max(
        len(source_tokens), len(canonical_tokens))
    score = .45 * spaced + .45 * compact + .10 * count
    if len(source_tokens) > len(canonical_tokens):
        score = max(score, _jaro_winkler(source.replace(" ", ""),
                                        canonical.replace(" ", "")))
    return score


def _jaro_winkler(source, target):
    """Character evidence for ASR token splits/merges; returns a 0..1 score."""
    if source == target:
        return 1.
    if not source or not target:
        return 0.
    radius = max(len(source), len(target)) // 2 - 1
    source_match = [False] * len(source)
    target_match = [False] * len(target)
    matches = 0
    for source_index, char in enumerate(source):
        for target_index in range(max(0, source_index - radius),
                                  min(source_index + radius + 1, len(target))):
            if not target_match[target_index] and char == target[target_index]:
                source_match[source_index] = True
                target_match[target_index] = True
                matches += 1
                break
    if not matches:
        return 0.
    source_chars = [char for char, matched in zip(source, source_match) if matched]
    target_chars = [char for char, matched in zip(target, target_match) if matched]
    transpositions = sum(left != right for left, right in zip(source_chars, target_chars)) / 2
    jaro = (matches / len(source) + matches / len(target)
            + (matches - transpositions) / matches) / 3
    prefix = 0
    for left, right in zip(source, target):
        if left != right or prefix == 4:
            break
        prefix += 1
    return jaro + prefix * .1 * (1 - jaro)


def _edit_distance(source, target):
    previous = list(range(len(target) + 1))
    for source_index, source_char in enumerate(source, 1):
        current = [source_index]
        for target_index, target_char in enumerate(target, 1):
            current.append(min(current[-1] + 1, previous[target_index] + 1,
                               previous[target_index - 1] + (source_char != target_char)))
        previous = current
    return previous[-1]


def _parse_glossary(document, label, config, start_order):
    if not isinstance(document, dict) or not isinstance(document.get("terms"), list):
        raise ValueError(f"Glossary {label} must contain a terms array")
    result = []
    for offset, item in enumerate(document["terms"]):
        if not isinstance(item, dict) or not isinstance(item.get("canonical"), str):
            raise ValueError(f"Invalid glossary entry in {label}")
        canonical = item["canonical"].strip()
        variants = tuple(item.get("variants", ()))
        aliases = tuple(item.get("aliases", ()))
        policy = item.get("auto_apply", "exact")
        if not canonical or policy not in POLICIES:
            raise ValueError(f"Invalid canonical term or auto_apply policy in {label}")
        if not all(isinstance(value, str) and value.strip() for value in variants + aliases):
            raise ValueError(f"Variants and aliases must be non-empty strings in {label}")
        auto = float(item.get("auto_threshold", config.auto_threshold))
        suggest = float(item.get("suggest_threshold", config.suggest_threshold))
        if not 0 <= suggest < auto <= 1:
            raise ValueError(f"Invalid thresholds for {canonical} in {label}")
        canonical_tokens = _tokens(canonical)
        if not canonical_tokens:
            raise ValueError(f"Canonical term has no words: {canonical}")
        result.append(_Term(canonical, canonical_tokens, variants, aliases, policy,
                            auto, suggest, start_order + offset))
    return result


def _load_glossary(path, config, start_order):
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Glossary not found: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return _parse_glossary(document, str(path), config, start_order)


class TerminologyNormalizer:
    def __init__(self, terms, config=None):
        self.config = config or NormalizerConfig()
        self.terms = tuple(terms)
        self._exact = {}
        for term in self.terms:
            forms = [(term.canonical, "canonical_form")]
            forms.extend((value, "exact_variant") for value in term.variants)
            forms.extend((value, "exact_alias") for value in term.aliases)
            for value, rule in forms:
                key = _tokens(value)
                existing = self._exact.get(key)
                if existing and existing[0].canonical != term.canonical:
                    raise ValueError(f"Ambiguous glossary form: {value}")
                self._exact[key] = (term, rule)
        self.reset()

    @classmethod
    def from_config(cls, config=None):
        config = config or NormalizerConfig.from_env()
        terms = _load_glossary(config.medical_glossary, config, 0)
        terms += _load_glossary(config.conference_glossary, config, len(terms))
        return cls(terms, config)

    @classmethod
    def from_documents(cls, documents, config=None):
        """Build from already decoded glossary documents, useful for validation/tests."""
        config = config or NormalizerConfig()
        terms = []
        for index, document in enumerate(documents):
            terms += _parse_glossary(document, f"document[{index}]", config, len(terms))
        return cls(terms, config)

    def reset(self):
        self._previous_id = None
        self._previous_raw = ""

    def _exact_matches(self, text, tokens):
        candidates = []
        for start in range(len(tokens)):
            for pattern, (term, rule) in self._exact.items():
                end = start + len(pattern)
                if end > len(tokens) or tuple(t.normalized for t in tokens[start:end]) != pattern:
                    continue
                if not _valid_span(text, tokens, start, end):
                    continue
                action = "suggest" if term.policy == "suggest" else "auto"
                candidates.append(_Match(start, end, tokens[start].start, tokens[end - 1].end,
                                         term, 1., rule, action))
        return candidates

    def _fuzzy_matches(self, text, tokens):
        candidates = []
        for term in self.terms:
            if term.policy == "exact":
                continue
            single_technical = (len(term.canonical_tokens) == 1
                                and term.policy in {"fuzzy", "suggest"}
                                and len(term.canonical_tokens[0])
                                >= self.config.collapsed_min_characters)
            if len(term.canonical_tokens) < 2 and not single_technical:
                continue
            low = 2 if single_technical else len(term.canonical_tokens)
            high = len(term.canonical_tokens) + self.config.max_token_delta
            for length in range(low, high + 1):
                # A technical one-word canonical may match a split ASR span, but
                # arbitrary one-word fuzzy matching remains disabled.
                if single_technical and length == 1:
                    continue
                for start in range(0, len(tokens) - length + 1):
                    end = start + length
                    if not _valid_span(text, tokens, start, end):
                        continue
                    confidence = _score(tuple(t.normalized for t in tokens[start:end]),
                                        term.canonical_tokens)
                    if single_technical:
                        compact_source = "".join(
                            token.normalized for token in tokens[start:end])
                        distance = _edit_distance(compact_source, term.canonical_tokens[0])
                        if distance <= self.config.collapsed_max_edits:
                            confidence = max(confidence, term.auto_threshold)
                    if confidence < term.suggest_threshold:
                        continue
                    action = ("auto" if term.policy == "fuzzy"
                              and confidence >= term.auto_threshold else "suggest")
                    candidates.append(_Match(start, end, tokens[start].start,
                                             tokens[end - 1].end, term, confidence,
                                             "glossary_fuzzy", action))
        return candidates

    @staticmethod
    def _spacing_corrections(text, reserved):
        corrections = []

        def overlaps(start, end):
            return any((start < reserved_end and end > reserved_start)
                       or (start == end and reserved_start < start < reserved_end)
                       for reserved_start, reserved_end in reserved)

        for match in re.finditer(r"\s+", text):
            start, end = match.span()
            if overlaps(start, end):
                continue
            following = text[end:end + 1]
            replacement = ("" if start == 0 or end == len(text)
                           or following in ",.;:!?" else " ")
            if match.group() != replacement:
                corrections.append(Correction(
                    match.group(), replacement, start, end,
                    "deterministic_spacing", 1., None))

        missing_space = re.compile(r"[,;:!?](?=[^\W_\d])", re.UNICODE)
        for match in missing_space.finditer(text):
            position = match.end()
            if not overlaps(position, position):
                corrections.append(Correction(
                    "", " ", position, position,
                    "deterministic_spacing", 1., None))
        return corrections

    @staticmethod
    def _select(candidates, reserved=()):
        selected = []
        occupied = set(reserved)
        ordered = sorted(candidates, key=lambda match: (
            0 if match.action == "auto" else 1,
            -match.confidence,
            -(match.end_token - match.start_token),
            match.start_token,
            match.term.order,
            match.term.canonical,
        ))
        for match in ordered:
            span = set(range(match.start_token, match.end_token))
            if span & occupied:
                continue
            selected.append(match)
            occupied.update(span)
        return sorted(selected, key=lambda match: match.start)

    def _cross_segment_suggestions(self, current_text):
        if not self._previous_raw:
            return ()
        previous_tokens = _source_tokens(self._previous_raw)
        start_word = max(0, len(previous_tokens) - self.config.context_words)
        previous_start = previous_tokens[start_word].start if previous_tokens else 0
        context = self._previous_raw[previous_start:] + " " + current_text
        boundary = len(self._previous_raw[previous_start:])
        tokens = _source_tokens(context)
        candidates = self._exact_matches(context, tokens) + self._fuzzy_matches(context, tokens)
        crossing = []
        for match in candidates:
            if not match.start < boundary < match.end:
                continue
            left = "".join(_tokens(context[match.start:boundary]))
            right = "".join(_tokens(context[boundary:match.end]))
            if len(left) >= 2 and len(right) >= 2:
                crossing.append(match)
        suggestions = []
        for match in self._select(crossing):
            source = context[match.start:match.end]
            if source == _case_like(source, match.term.canonical):
                continue
            suggestions.append(Suggestion(
                source=source, candidate=match.term.canonical,
                start=None, end=max(0, match.end - boundary - 1),
                rule="cross_segment_" + match.rule,
                confidence=round(match.confidence, 6), cross_segment=True,
                previous_segment_id=self._previous_id))
        return tuple(suggestions)

    def normalize(self, segment_id, raw_text):
        started = time.perf_counter_ns()
        tokens = _source_tokens(raw_text)
        exact = self._select(self._exact_matches(raw_text, tokens))
        exact_spans = {index for match in exact for index in range(match.start_token, match.end_token)}
        fuzzy = self._select(self._fuzzy_matches(raw_text, tokens), exact_spans)
        selected = sorted(exact + fuzzy, key=lambda match: match.start)
        corrections = []
        suggestions = []
        known = []
        for match in selected:
            source = raw_text[match.start:match.end]
            replacement = _case_like(source, match.term.canonical)
            if match.action == "auto":
                if source != replacement:
                    corrections.append(Correction(
                        source, replacement, match.start, match.end, match.rule,
                        round(match.confidence, 6), match.term.canonical))
                known.append(match.term.canonical)
            else:
                suggestions.append(Suggestion(
                    source, match.term.canonical, match.start, match.end,
                    match.rule, round(match.confidence, 6)))
        suggestions.extend(self._cross_segment_suggestions(raw_text))
        reserved = tuple((correction.start, correction.end) for correction in corrections)
        corrections.extend(self._spacing_corrections(raw_text, reserved))
        corrections.sort(key=lambda correction: (correction.start, correction.end))
        normalized = raw_text
        for correction in reversed(corrections):
            normalized = (normalized[:correction.start] + correction.replacement
                          + normalized[correction.end:])
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        result = NormalizedSegment(
            str(segment_id), raw_text, normalized, tuple(corrections),
            tuple(suggestions), tuple(dict.fromkeys(known)), round(elapsed, 6))
        self._previous_id, self._previous_raw = str(segment_id), raw_text
        return result

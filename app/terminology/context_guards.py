"""Context rules promoted from the frozen laboratory; originals retained."""
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig, _tokens
from .lexical import tokens, measurement_signatures, NEGATIONS, NUMBER_WORDS, UNITS

FUNCTION_WORDS = set("a an the by of with without and or for to from in on at into onto upon over under between during through before after as than that which who is are was were be been being has have had do does did this these those it its their our your his her any each both either neither not no never nor only also then if while when where so yet can could may might must should will would".split())

CONTRAST_GROUPS = [
    {"primary", "secondary"}, {"systolic", "diastolic"}, {"sodium", "potassium"},
    {"left", "right"}, {"high", "low"}, {"treated", "untreated"}, {"controlled", "uncontrolled"},
    {"american", "european"}, {"event", "events"}, {"receptor", "receptors"},
    {"inhibitor", "inhibitors"}, {"salt", "salts"},
]

def ratio(a, b):
    return SequenceMatcher(None, a, b).ratio()

def quantity_signature(text):
    return dict(number_words=[w for w in tokens(text) if w in NUMBER_WORDS],
                raw_measurements=[m["value"] for m in measurement_signatures(text)],
                unit_tokens=[w for w in tokens(text) if w in UNITS])

def token_alignment(source, target):
    """Consume every token; permit spelling fragments, never a dropped neighbor."""
    @lru_cache(None)
    def walk(i, j):
        if j == len(target):
            return () if i == len(source) else None
        for width in (1, 2, 3):
            group = source[i:i+width]
            if len(group) != width:
                continue
            joined = "".join(group); word = target[j]
            if word in FUNCTION_WORDS or word in NUMBER_WORDS or word in UNITS or any(c.isdigit() for c in word):
                if width != 1 or joined != word:
                    continue
            elif joined != word:
                if ratio(joined, word) < .65:
                    continue
                if width > 1 and any(ratio(fragment, word) >= .85 for fragment in group):
                    # A nearly complete word plus another token is not a split.
                    continue
            rest = walk(i+width, j+1)
            if rest is not None:
                return ((tuple(group), word),)+rest
        return None
    return walk(0, 0)

def guard_span(text, start, end, canonical):
    source = text[start:end]; a, b = _tokens(source), _tokens(canonical)
    reasons = []
    if not (0 <= start < end <= len(text)):
        return dict(accepted=False, reasons=["invalid_span"], alignment=None)
    if (start and (text[start-1].isalnum() or text[start-1] in "_'’")) or (
            end < len(text) and (text[end].isalnum() or text[end] in "_'’")):
        reasons.append("whole_word_or_identifier_boundary")
    if [w for w in a if w in FUNCTION_WORDS] != [w for w in b if w in FUNCTION_WORDS]:
        reasons.append("function_word_sequence_changed")
    if [w for w in tokens(source) if w in NEGATIONS] != [w for w in tokens(canonical) if w in NEGATIONS]:
        reasons.append("negation_changed")
    if quantity_signature(source) != quantity_signature(canonical):
        reasons.append("literal_quantity_or_unit_changed")
    for group in CONTRAST_GROUPS:
        incoming, outgoing = [w for w in a if w in group], [w for w in b if w in group]
        if incoming and incoming != outgoing:
            reasons.append("opposed_qualifier_or_grammatical_number_changed")
            break
    for word in a:
        for prefix in ("non", "un"):
            if word.startswith(prefix) and word[len(prefix):] in b and word not in b:
                reasons.append("morphological_negation_changed")
    anchors = [w for w in a if w in b and len(w) >= 3 and w not in FUNCTION_WORDS]
    if not anchors:
        reasons.append("no_unchanged_lexical_anchor")
    alignment = token_alignment(a, b)
    if alignment is None:
        reasons.append("no_lossless_token_alignment")
    return dict(accepted=not reasons, reasons=sorted(set(reasons)), alignment=alignment)

class ContextNormalizer(TerminologyNormalizer):
    """Promoted conservative preselection guards for the soft-testing release."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guard_audit = []

    def _screen_matches(self, text, matches):
        accepted = []
        for match in matches:
            guard = guard_span(text, match.start, match.end, match.term.canonical)
            if guard["accepted"]:
                accepted.append(match)
            else:
                self.guard_audit.append(dict(source=text[match.start:match.end], canonical=match.term.canonical,
                    start=match.start, end=match.end, confidence=match.confidence, action=match.action, rule=match.rule, **guard))
        return accepted

    def _exact_matches(self, text, source_tokens):
        return self._screen_matches(text,super()._exact_matches(text,source_tokens))

    def _fuzzy_matches(self, text, source_tokens):
        return self._screen_matches(text,super()._fuzzy_matches(text,source_tokens))

def document(selected, thresholds):
    terms=[]
    for item in selected:
        threshold=thresholds[item["concept_id"]]
        term=dict(canonical=item["canonical_en"], auto_apply="exact" if threshold is None else "fuzzy")
        if threshold is not None:
            term.update(auto_threshold=threshold, suggest_threshold=min(.86,threshold-.01))
        terms.append(term)
    return dict(terms=terms)

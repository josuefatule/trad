"""Exact edit metrics and auditable lexical risk flags (not clinical adjudication)."""
from collections import Counter
import re
import unicodedata

NORMALIZATION = {
    "version": 1, "unicode": "NFKC + casefold; curly apostrophes to ASCII",
    "tokens": "Unicode words with internal apostrophes; numbers retain internal decimal/comma/slash/colon; other punctuation/hyphens become boundaries",
    "numbers": "No conversion of spoken numbers to digits, no unit expansion, no glossary on references",
    "cer": "Exact Levenshtein over normalized text joined by single spaces, including spaces",
    "clinical_limit": "Primary lexical scores omit punctuation signs; raw signed/comparator/percent measurement signatures are reviewed separately",
    "empty_reference": "Both empty=0; nonempty hypothesis with empty reference=undefined (null)",
}
TOKEN = re.compile(r"\d+(?:[.,:/]\d+)*|[^\W\d_]+(?:'[^\W\d_]+)*", re.UNICODE)
NEGATIONS = set("no not never without neither nor denies denied negative absence absent cannot unlikely".split())
NUMBER_WORDS = set("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred thousand half quarter first second third".split())
UNITS = set("mg mcg µg μg g kg ml l mmhg mmol mol bpm hz percent percentage milligram milligrams microgram micrograms milliliter milliliters millimetres millimeters mercury".split())
OPPOSED = [{"left", "right"}, {"positive", "negative"}, {"hyperkalemia", "hypokalemia"},
           {"hypertension", "hypotension"}, {"high", "low"}, {"systolic", "diastolic"}]
DRUG_CUES = set("enalapril lisinopril ramipril losartan valsartan candesartan spironolactone eplerenone furosemide dapagliflozin empagliflozin metoprolol carvedilol amlodipine hydrochlorothiazide chlorthalidone".split())
MEASUREMENT=re.compile(r"[<>≤≥]?\s*[+−-]?\d+(?:[.,:/]\d+)*(?:\s*(?:mmol/l|mmhg|mcg|µg|μg|mg|kg|ml|bpm|%|g|l)\b|\s*%)?",re.I)


def measurement_signatures(text):
    """Literal review channel: catches signs/percent omitted by lexical WER.

    Formatting or spoken/digit differences can also trigger it. Not a semantic
    equivalence checker, dose validator or certified medical-error count.
    """
    text=unicodedata.normalize('NFKC',text).casefold().replace('−','-')
    return [{'value':re.sub(r'\s+','',m.group()),'start':m.start(),'end':m.end()} for m in MEASUREMENT.finditer(text)]


def tokens(text):
    text = unicodedata.normalize("NFKC", text).casefold().replace("’", "'").replace("‘", "'")
    return TOKEN.findall(text)


def edit_distance(a, b):
    """Myers bit-vector Levenshtein, exact; avoids quadratic CER matrices."""
    if len(a) > len(b): a, b = b, a
    if not a: return len(b)
    mask = (1 << len(a)) - 1
    highest = 1 << (len(a) - 1)
    eq = {}
    for i, value in enumerate(a): eq[value] = eq.get(value, 0) | (1 << i)
    positive, negative, score = mask, 0, len(a)
    for value in b:
        equal = eq.get(value, 0)
        xv = equal | negative
        xh = (((equal & positive) + positive) ^ positive) | equal
        ph = negative | ~(xh | positive)
        mh = positive & xh
        if ph & highest: score += 1
        elif mh & highest: score -= 1
        ph, mh = (ph << 1) | 1, mh << 1
        positive, negative = (mh | ~(xv | ph)) & mask, (ph & xv) & mask
    return score


def word_alignment(reference, hypothesis):
    """Exact DP with deterministic tie break match/substitute, delete, insert.

    Two cost rows and one byte per backtrace cell; counts may depend on tie break
    but total distance and WER do not. No heuristic diff used for scoring.
    """
    n, m = len(reference), len(hypothesis)
    previous = list(range(m + 1))
    trace = [bytearray(m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1): trace[0][j] = 2
    for i, r in enumerate(reference, 1):
        current = [i] + [0] * m; trace[i][0] = 1
        for j, h in enumerate(hypothesis, 1):
            diagonal = previous[j - 1] + (r != h)
            deletion, insertion = previous[j] + 1, current[j - 1] + 1
            if diagonal <= deletion and diagonal <= insertion: current[j] = diagonal
            elif deletion <= insertion: current[j] = deletion; trace[i][j] = 1
            else: current[j] = insertion; trace[i][j] = 2
        previous = current
    i, j, edits = n, m, []
    while i or j:
        op = trace[i][j]
        if op == 0:
            i -= 1; j -= 1
            if reference[i] != hypothesis[j]: edits.append({"op": "S", "ref_index": i, "hyp_index": j, "reference": reference[i], "hypothesis": hypothesis[j]})
        elif op == 1:
            i -= 1; edits.append({"op": "D", "ref_index": i, "hyp_index": j, "reference": reference[i], "hypothesis": ""})
        else:
            j -= 1; edits.append({"op": "I", "ref_index": i, "hyp_index": j, "reference": "", "hypothesis": hypothesis[j]})
    edits.reverse()
    return previous[m], edits


def risk_categories(words):
    values = set(words); result = []
    if values & NEGATIONS: result.append("negation_cue")
    if values & NUMBER_WORDS or any(any(c.isdigit() for c in w) for w in values): result.append("number_or_numeric_word")
    if values & UNITS: result.append("unit")
    if values & DRUG_CUES: result.append("medication_cue")
    if any(values & pair for pair in OPPOSED): result.append("clinical_polarity_or_laterality_cue")
    return result


def metrics(reference_text, hypothesis_text):
    ref, hyp = tokens(reference_text), tokens(hypothesis_text)
    distance, edits = word_alignment(ref, hyp)
    counts = Counter(e["op"] for e in edits)
    rtext, htext = " ".join(ref), " ".join(hyp)
    chars = edit_distance(rtext, htext)
    flagged = []
    for e in edits:
        categories = risk_categories([e["reference"], e["hypothesis"]])
        context_words=ref[max(0,e['ref_index']-3):e['ref_index']+4]+hyp[max(0,e['hyp_index']-3):e['hyp_index']+4]
        context_flags=risk_categories(context_words)
        if 'unit' in context_flags and 'number_or_numeric_word' in context_flags:
            categories.append('dose_or_measurement_context')
        if categories:
            flagged.append({**e, "categories": categories,
                "reference_context": " ".join(ref[max(0, e["ref_index"]-4):e["ref_index"]+5]),
                "hypothesis_context": " ".join(hyp[max(0, e["hyp_index"]-4):e["hyp_index"]+5])})
    ref_measurements,hyp_measurements=measurement_signatures(reference_text),measurement_signatures(hypothesis_text)
    return {"reference_normalized": rtext, "hypothesis_normalized": htext,
        "reference_words": len(ref), "hypothesis_words": len(hyp),
        "substitutions": counts["S"], "deletions": counts["D"], "insertions": counts["I"],
        "word_errors": distance, "wer": distance / len(ref) if ref else (0. if not hyp else None),
        "reference_characters": len(rtext), "character_errors": chars,
        "cer": chars / len(rtext) if rtext else (0. if not htext else None),
        "word_edits": edits, "risk_policy_version":2, "risk_flags": flagged,
        "measurement_signature_review":{"reference":ref_measurements,"hypothesis":hyp_measurements,
            "changed":[m['value'] for m in ref_measurements]!=[m['value'] for m in hyp_measurements],
            "policy":"literal raw signature mismatch needs human review; may be formatting, not clinical error"},
        "risk_flag_counts": dict(Counter(c for e in flagged for c in e["categories"]))}


def term_inventory(reference, hypothesis, terms):
    """Exact token-form occurrence deficits; not clinical error certification."""
    ref, hyp = tokens(reference), tokens(hypothesis)
    def count(sequence, forms):
        spans = set()
        for form in forms:
            if form:
                for i in range(len(sequence)-len(form)+1):
                    if sequence[i:i+len(form)] == form: spans.add((i, i+len(form)))
        # Prefer longest match at a location; no aliases modifying the transcript.
        selected = []; end = -1
        for start, stop in sorted(spans, key=lambda p:(p[0],-p[1])):
            if start >= end: selected.append((start,stop));end=stop
        return len(selected)
    rows = []
    for t in terms:
        forms = [tokens(v) for v in [t["canonical"], *t.get("aliases", []), *t.get("variants", [])]]
        r, h = count(ref, forms), count(hyp, forms)
        if r or h: rows.append({"canonical":t["canonical"],"reference_occurrences":r,
            "hypothesis_occurrences":h,"occurrence_deficit":max(0,r-h),"occurrence_excess":max(0,h-r)})
    return rows

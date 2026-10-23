"""Read-only audit and unapproved shadow normalizer; never loads LIVE env."""
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from app.captions.terminology_normalizer import (
    NormalizerConfig, TerminologyNormalizer, _tokens, _score,
)
from .metrics import risk_categories, tokens, metrics


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def audit(path):
    raw = Path(path).read_bytes(); document = load(path)
    terms = document.get("terms", [])
    exact = defaultdict(set)
    for term in terms:
        for form in [term["canonical"], *term.get("variants", []), *term.get("aliases", [])]:
            exact[_tokens(form)].add(term["canonical"])
    collisions = [{"form_tokens":list(k),"canonicals":sorted(v)} for k,v in exact.items() if len(v)>1]
    fuzzy_collisions = []
    for i, source in enumerate(terms):
        for target in terms[i+1:]:
            a,b=_tokens(source["canonical"]),_tokens(target["canonical"])
            if a==b: continue
            score=_score(a,b)
            if score >= min(float(source.get("suggest_threshold",.86)),float(target.get("suggest_threshold",.86))):
                fuzzy_collisions.append({"a":source["canonical"],"b":target["canonical"],"score":round(score,6),
                    "risk_categories":risk_categories([*a,*b]),
                    "scope":"screening canonical pair only; not proof that runtime span matcher applies it"})
    try:
        TerminologyNormalizer.from_documents([document], NormalizerConfig())
        compatible, error = True, None
    except Exception as exc: compatible,error=False,str(exc)
    demo={"terms":[{"canonical":"hypertension","auto_apply":"fuzzy","auto_threshold":.99,"suggest_threshold":.86}]}
    boosted=_threshold_demo(demo,"hyper tenson")
    sensitive = [{"canonical":t["canonical"],"policy":t.get("auto_apply","exact"),"flags":risk_categories(tokens(t["canonical"]))}
                 for t in terms if risk_categories(tokens(t["canonical"]))]
    sensitive_forms=[]
    for t in terms:
        canonical=tokens(t['canonical'])
        for form in [*t.get('aliases',[]),*t.get('variants',[])]:
            source=tokens(form);flags=risk_categories(source+canonical)
            if flags and source!=canonical:sensitive_forms.append({'source':form,'canonical':t['canonical'],'flags':flags,'policy':t.get('auto_apply','exact'),'action':'manual review required'})
    return {"source":str(Path(path).resolve()),"sha256":hashlib.sha256(raw).hexdigest(),"term_count":len(terms),
        "policies":dict(Counter(t.get("auto_apply","exact") for t in terms)),"schema_compatible":compatible,"load_error":error,
        "exact_collisions":collisions,"fuzzy_canonical_screening":fuzzy_collisions,"sensitive_entries":sensitive,
        "sensitive_forms":sensitive_forms,
        "normalizer_source_sha256":hashlib.sha256(Path(__import__('inspect').getfile(TerminologyNormalizer)).read_bytes()).hexdigest(),
        "algorithm_findings":[
            "exact variants/aliases auto-apply with confidence 1, regardless of auto_threshold",
            "single-word fuzzy canonicals do not match isolated words; split technical words may match",
            "collapsed edit-distance path can raise confidence to the configured auto_threshold; 0.99 is not a calibrated probability",
            "casefold + diacritic removal + hyphen/space joins affect collisions; multiword fuzzy uses conservative asymmetric span lengths",
            "suggest never applies term replacements, but deterministic spacing still runs",
            "all clinical replacements require review; exact compatibility is not clinical safety"],
        "threshold_099_demo":boosted,
        "live_activation":"NOT authorized or performed",
        "asr_context_support":{"faster_whisper":"initial_prompt is explicit and implemented in installed transcribe; optional lab experiment only",
            "wlk":"must inspect installed query and decoder-context path; no context injection assumed"}}


def _threshold_demo(document,text):
    item=TerminologyNormalizer.from_documents([document],NormalizerConfig()).normalize("demo",text)
    return {"input":text,"output":item.normalized_text,"corrections":[asdict(c) for c in item.corrections],
        "uncalibrated_score_before_boost":_score(_tokens(text),_tokens(document["terms"][0]["canonical"]))}


def shadow(reference,hypothesis,document,segment_id):
    try:
        result=TerminologyNormalizer.from_documents([document],NormalizerConfig()).normalize(segment_id,hypothesis)
    except Exception as exc:
        return {"status":"blocked","reason":str(exc)}
    changes=[]
    for change in result.corrections:
        value=asdict(change)
        value["risk_categories"]=risk_categories(tokens(change.source)+tokens(change.replacement))
        value["approval"]="spacing_only" if change.rule=="deterministic_spacing" else "human_review_required"
        changes.append(value)
    # Controlled output never applies an unreviewed terminological replacement.
    controlled=hypothesis
    for c in sorted((c for c in result.corrections if c.rule=="deterministic_spacing"),key=lambda c:c.start,reverse=True):
        controlled=controlled[:c.start]+c.replacement+controlled[c.end:]
    return {"status":"shadow_only_unapproved","candidate_text":result.normalized_text,
        "candidate_metrics":metrics(reference,result.normalized_text),"controlled_text":controlled,
        "controlled_metrics":metrics(reference,controlled),"corrections":changes,
        "suggestions":[asdict(s) for s in result.suggestions],"controlled_policy":"spacing only; no unreviewed medical replacements"}

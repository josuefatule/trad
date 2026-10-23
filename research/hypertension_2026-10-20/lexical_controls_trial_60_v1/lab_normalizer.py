"""Experimental policies only. No application files or glossary writes."""
from dataclasses import asdict
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
ROOT=BASE.parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(BASE/'context_boundary_trial_10_v1'))
import evaluate_context as ctx
from app.captions.terminology_normalizer import _source_tokens, _tokens, _valid_span, _case_like

PROFILES={
    'variants_only':(True,False,False),
    'variants_and_number':(True,True,False),
    'all_fixes':(True,True,True),
}
IRREGULAR={'person':'people','child':'children','man':'men','woman':'women',
           'foot':'feet','tooth':'teeth','index':'indices','analysis':'analyses',
           'diagnosis':'diagnoses','basis':'bases','crisis':'crises'}


def plural_spellings(word):
    """Conservative no-rewrite detector, not an inflection/translation engine."""
    if len(word)<3:return set()
    if word in IRREGULAR:return {IRREGULAR[word]}
    if word.endswith('sis'):return {word[:-2]+'es'}
    if word.endswith('y') and word[-2] not in 'aeiou':return {word[:-1]+'ies'}
    if word.endswith(('s','x','z','ch','sh')):return {word+'es'}
    return {word+'s'}


def number_changes(source,target):
    pairs=[]
    for a in _tokens(source):
        for b in _tokens(target):
            if a!=b and (a in plural_spellings(b) or b in plural_spellings(a)):
                pairs.append((a,b))
    return sorted(set(pairs))


def valid_outer_boundary(text,start,end):
    return not ((start and (text[start-1].isalnum() or text[start-1] in "_'’")) or
                (end<len(text) and (text[end].isalnum() or text[end] in "_'’")))


def preservation_spans(text,records):
    source=_source_tokens(text);rows=[]
    for record in records:
        pattern=_tokens(record['form'])
        for start in range(len(source)-len(pattern)+1):
            end=start+len(pattern)
            if tuple(t.normalized for t in source[start:end])!=pattern:continue
            a,b=source[start].start,source[end-1].end
            if _valid_span(text,source,start,end) and valid_outer_boundary(text,a,b):
                rows.append(dict(start=a,end=b,source=text[a:b],form_id=record['form_id'],
                    concept_id=record['concept_id'],preservation_only=True,automatic_substitution_approved=False))
    return rows


def contained_pattern(short,long):
    return len(short)<len(long) and any(tuple(long[i:i+len(short)])==tuple(short)
                                      for i in range(len(long)-len(short)+1))


class LaboratoryNormalizer(ctx.ContextNormalizer):
    def configure(self,profile,variants,text):
        self.variant_policy,self.number_policy,self.overlap_policy=PROFILES[profile]
        self.preserved=preservation_spans(text,variants) if self.variant_policy else []
        self.overlap_audit=[]
        return self

    def _screen_matches(self,text,matches):
        accepted=[]
        for match in matches:
            source=text[match.start:match.end]
            verdict=ctx.guard_span(text,match.start,match.end,match.term.canonical)
            reasons=list(verdict['reasons'])
            if self.variant_policy and any(match.start<p['end'] and match.end>p['start'] for p in self.preserved):
                reasons.append('preserve_registered_variant_no_rewrite')
            pairs=number_changes(source,match.term.canonical) if self.number_policy else []
            if pairs:reasons.append('preserve_singular_plural_both_directions')
            if reasons:
                self.guard_audit.append(dict(source=source,canonical=match.term.canonical,start=match.start,end=match.end,
                    confidence=match.confidence,rule=match.rule,action=match.action,
                    accepted=False,reasons=sorted(set(reasons)),number_pairs=pairs))
            else:accepted.append(match)
        return accepted

    def select_with_subphrases(self,text,exact,fuzzy):
        """Preempt only proper exact subphrases of an accepted AUTO candidate.

        Unrelated or larger exact terms, protected variants and rejected spans
        cannot be displaced. Existing confidence ordering resolves competitors.
        """
        eligible=[]
        for match in fuzzy:
            if match.action!='auto':continue
            overlapping=[e for e in exact if match.start<e.end and match.end>e.start]
            if not overlapping:continue
            if all(match.start<=e.start and match.end>=e.end and
                   contained_pattern(e.term.canonical_tokens,match.term.canonical_tokens) for e in overlapping):
                eligible.append(match)
        promoted=self._select(eligible)
        remaining_exact=[]
        for e in exact:
            blockers=[m for m in promoted if m.start<e.end and m.end>e.start]
            if blockers:
                self.overlap_audit.append(dict(exact_source=text[e.start:e.end],exact_canonical=e.term.canonical,
                    start=e.start,end=e.end,promoted_canonicals=[m.term.canonical for m in blockers],
                    reason='proper_exact_subphrase_within_guarded_auto_phrase'))
            else:remaining_exact.append(e)
        reserved={i for m in promoted+remaining_exact for i in range(m.start_token,m.end_token)}
        others=self._select(fuzzy,reserved)
        return sorted(promoted+remaining_exact+others,key=lambda m:m.start)


def candidate(text,selected,thresholds,variants,profile='all_fixes'):
    started=time.perf_counter_ns()
    obj=LaboratoryNormalizer.from_documents([ctx.document(selected,thresholds)],ctx.NormalizerConfig())
    obj.configure(profile,variants,text)
    source=_source_tokens(text)
    exact=obj._select(obj._exact_matches(text,source))
    fuzzy=obj._fuzzy_matches(text,source)
    if obj.overlap_policy:selected_matches=obj.select_with_subphrases(text,exact,fuzzy)
    else:
        reserved={i for m in exact for i in range(m.start_token,m.end_token)}
        selected_matches=sorted(exact+obj._select(fuzzy,reserved),key=lambda m:m.start)
    changes=[]
    for match in selected_matches:
        incoming=text[match.start:match.end]
        replacement=_case_like(incoming,match.term.canonical)
        if match.action=='auto' and incoming!=replacement:
            changes.append(dict(source=incoming,replacement=replacement,start=match.start,end=match.end,
                rule=match.rule,confidence=round(match.confidence,6),canonical=match.term.canonical))
    output=text
    for change in reversed(changes):
        assert text[change['start']:change['end']]==change['source']
        output=output[:change['start']]+change['replacement']+output[change['end']:]
    return dict(text=output,controlled_text=text,changes=changes,blocked=obj.guard_audit,
        preserved_variants=obj.preserved,overlap_resolutions=obj.overlap_audit,
        wall_ms=(time.perf_counter_ns()-started)/1_000_000,
        policy='Laboratory only; immutable raw input; no application integration')

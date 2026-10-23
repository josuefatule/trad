"""Refined directional gate; runtime contains no research imports."""
import time
from functools import lru_cache
from . import pressure_base as first
from . import boundary_policy as previous
from app.captions.terminology_normalizer import _source_tokens, _case_like, _tokens
from .lexical import edit_distance

first.previous=previous

@lru_cache(maxsize=65536)
def direction_signature(text):
    original=first.direction_signature(text);markers=[]
    for marker in original['markers']:
        current=dict(marker)
        if current['direction']=='AMBIGUOUS':
            word=''.join(_tokens(current['source']))
            for prefix in first.PREFIXES[1:]:
                if word.startswith(prefix) and len(word)>len(prefix)+6:
                    word=word[len(prefix):];break
            direction='HYPER' if word.startswith('hyper') else 'HYPO' if word.startswith('hypo') else None
            if direction and min(edit_distance(word,w) for w in first.BASE_WORDS[direction][:2])<=2:
                current['direction']=direction
                current['basis']='explicit_direction_root_with_at_most_two_suffix_spelling_edits'
        markers.append(current)
    return dict(directions=[m['direction'] for m in markers],markers=markers,
        ambiguous=any(m['direction']=='AMBIGUOUS' for m in markers))

def direction_verdict(source,target):
    a=direction_signature(source);b=direction_signature(target)
    accepted=not a['ambiguous'] and not b['ambiguous'] and a['directions']==b['directions']
    return dict(accepted=accepted,source_signature=a,target_signature=b,
                reason=None if accepted else 'pressure_direction_changed_or_unproven')

class PressureNormalizer(first.previous.BoundaryNormalizer):
    def _screen_matches(self,text,matches):
        kept=[]
        for m in matches:
            verdict=direction_verdict(text[m.start:m.end],m.term.canonical)
            if verdict['accepted']:kept.append(m)
            else:self.guard_audit.append(dict(source=text[m.start:m.end],canonical=m.term.canonical,
                start=m.start,end=m.end,confidence=m.confidence,rule=m.rule,action=m.action,
                accepted=False,reasons=[verdict['reason']],source_signature=verdict['source_signature'],target_signature=verdict['target_signature']))
        return super()._screen_matches(text,kept)

def candidate(text,selected,thresholds,variants):
    started=time.perf_counter_ns()
    obj=PressureNormalizer.from_documents([first.previous.first.ctx.document(selected,thresholds)],first.previous.first.ctx.NormalizerConfig())
    obj.configure('all_fixes',variants,text)
    source=_source_tokens(text)
    exact=obj._select(obj._exact_matches(text,source));fuzzy=obj._fuzzy_matches(text,source)
    exact=obj._select(obj._screen_matches(text,exact));matches=obj.select_with_subphrases(text,exact,fuzzy)
    changes=[]
    for m in matches:
        incoming=text[m.start:m.end];replacement=_case_like(incoming,m.term.canonical)
        if m.action=='auto' and incoming!=replacement:
            changes.append(dict(source=incoming,replacement=replacement,start=m.start,end=m.end,
                rule=m.rule,confidence=round(m.confidence,6),canonical=m.term.canonical))
    output=text
    for c in reversed(changes):
        assert text[c['start']:c['end']]==c['source']
        output=output[:c['start']]+c['replacement']+output[c['end']:]
    return dict(text=output,controlled_text=text,changes=changes,blocked=obj.guard_audit,
        preserved_variants=obj.preserved,identifier_protections=obj.identifier_spans,overlap_resolutions=obj.overlap_audit,
        wall_ms=(time.perf_counter_ns()-started)/1_000_000,policy='Visible-root refinement in laboratory only')

"""Laboratory-only directional preservation before exact/fuzzy selection."""
from pathlib import Path
import re
import sys
import time
from functools import lru_cache

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
sys.path.insert(0,str(BASE/'lexical_controls_trial_60_v1/boundary_refinement_v2'))
import boundary_normalizer as previous
from app.captions.terminology_normalizer import _source_tokens,_valid_span,_case_like
from trad_lab.metrics import edit_distance

PREFIXES=('','anti','non','pre','pseudo','post','un')
BASE_WORDS={'HYPER':('hypertension','hypertensive','hypertensions','hypertensives'),
            'HYPO':('hypotension','hypotensive','hypotensions','hypotensives')}
EXACT={prefix+word:direction for direction,words in BASE_WORDS.items() for word in words for prefix in PREFIXES}
VISIBLE=re.compile(r'^(?:anti|non|pre|pseudo|post|un)?(?P<root>hyper|hypo)ten[a-z]*$')


@lru_cache(maxsize=65536)
def direction_signature(text):
    """Preserve visible roots; join only attested spelling fragments.

    A near spelling without a visible directional root is explicitly ambiguous.
    This is a text-preservation rule, not a diagnosis or semantic classifier.
    """
    source=_source_tokens(text);markers=[];i=0
    while i<len(source):
        found=None
        for width in (3,2,1):
            end=i+width
            if end>len(source) or not _valid_span(text,source,i,end):continue
            joined=''.join(t.normalized for t in source[i:end])
            if joined in EXACT:
                found=(EXACT[joined],end);break
        if found is None:
            word=source[i].normalized;visible=VISIBLE.fullmatch(word)
            if visible:found=('HYPER' if visible.group('root')=='hyper' else 'HYPO',i+1)
            elif len(word)>=7:
                # Prefixes are stripped only to detect uncertainty, never to
                # approve dropping them from the actual replacement.
                root=word
                for prefix in PREFIXES[1:]:
                    if word.startswith(prefix) and len(word)>len(prefix)+6:
                        root=word[len(prefix):];break
                distances={direction:min(edit_distance(root,w) for w in words[:2]) for direction,words in BASE_WORDS.items()}
                if min(distances.values())<=2:found=('AMBIGUOUS',i+1)
        if found:
            direction,end=found
            markers.append(dict(direction=direction,start=source[i].start,end=source[end-1].end,
                source=text[source[i].start:source[end-1].end]))
            i=end
        else:i+=1
    return dict(directions=[m['direction'] for m in markers],markers=markers,
                ambiguous=any(m['direction']=='AMBIGUOUS' for m in markers))


def direction_verdict(source,target):
    incoming=direction_signature(source);outgoing=direction_signature(target)
    accepted=not incoming['ambiguous'] and not outgoing['ambiguous'] and incoming['directions']==outgoing['directions']
    return dict(accepted=accepted,source_signature=incoming,target_signature=outgoing,
        reason=None if accepted else 'pressure_direction_changed_or_unproven')


class PressureNormalizer(previous.BoundaryNormalizer):
    def _screen_matches(self,text,matches):
        kept=[]
        for match in matches:
            verdict=direction_verdict(text[match.start:match.end],match.term.canonical)
            if verdict['accepted']:kept.append(match)
            else:self.guard_audit.append(dict(source=text[match.start:match.end],canonical=match.term.canonical,
                start=match.start,end=match.end,confidence=match.confidence,rule=match.rule,action=match.action,
                accepted=False,reasons=[verdict['reason']],source_signature=verdict['source_signature'],target_signature=verdict['target_signature']))
        return super()._screen_matches(text,kept)


def candidate(text,selected,thresholds,variants):
    started=time.perf_counter_ns()
    obj=PressureNormalizer.from_documents([previous.first.ctx.document(selected,thresholds)],previous.first.ctx.NormalizerConfig())
    obj.configure('all_fixes',variants,text)
    source=_source_tokens(text)
    exact=obj._select(obj._exact_matches(text,source));fuzzy=obj._fuzzy_matches(text,source)
    exact=obj._select(obj._screen_matches(text,exact))
    matches=obj.select_with_subphrases(text,exact,fuzzy);changes=[]
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
        preserved_variants=obj.preserved,overlap_resolutions=obj.overlap_audit,identifier_protections=obj.identifier_spans,
        wall_ms=(time.perf_counter_ns()-started)/1_000_000,
        policy='New laboratory-only pressure-direction guard; original application and evidence unchanged')

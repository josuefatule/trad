"""Second laboratory revision: propagate a blocked identifier's full span."""
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import lab_normalizer as first
from app.captions.terminology_normalizer import _source_tokens, _case_like


class BoundaryNormalizer(first.LaboratoryNormalizer):
    def configure(self,*args,**kwargs):
        self.identifier_spans=[]
        return super().configure(*args,**kwargs)

    def _screen_matches(self,text,matches):
        # A high-scoring phrase that is otherwise admissible but starts inside
        # an identifier protects its complete span. Nested suffixes cannot evade
        # that rejection by beginning after a space or hyphen in the phrase.
        for match in matches:
            verdict=first.ctx.guard_span(text,match.start,match.end,match.term.canonical)
            if match.action=='auto' and set(verdict['reasons'])=={'whole_word_or_identifier_boundary'}:
                if self.number_policy and first.number_changes(text[match.start:match.end],match.term.canonical):continue
                key=(match.start,match.end,match.term.canonical)
                if not any((r['start'],r['end'],r['canonical'])==key for r in self.identifier_spans):
                    self.identifier_spans.append(dict(start=match.start,end=match.end,
                        source=text[match.start:match.end],canonical=match.term.canonical,
                        reason='propagate_identifier_boundary_to_full_candidate_phrase'))
        accepted=super()._screen_matches(text,matches)
        kept=[]
        for match in accepted:
            if any(match.start<r['end'] and match.end>r['start'] for r in self.identifier_spans):
                self.guard_audit.append(dict(source=text[match.start:match.end],canonical=match.term.canonical,
                    start=match.start,end=match.end,confidence=match.confidence,action=match.action,rule=match.rule,
                    accepted=False,reasons=['inside_identifier_protected_phrase']))
            else:kept.append(match)
        return kept


def candidate(text,selected,thresholds,variants,profile='all_fixes'):
    if profile!='all_fixes':return first.candidate(text,selected,thresholds,variants,profile)
    started=time.perf_counter_ns()
    obj=BoundaryNormalizer.from_documents([first.ctx.document(selected,thresholds)],first.ctx.NormalizerConfig())
    obj.configure(profile,variants,text)
    source=_source_tokens(text)
    exact=obj._select(obj._exact_matches(text,source))
    fuzzy=obj._fuzzy_matches(text,source)
    # Fuzzy screening may reveal a longer protected phrase around an exact
    # subterm already examined in the first pass.
    exact=obj._select(obj._screen_matches(text,exact))
    selected_matches=obj.select_with_subphrases(text,exact,fuzzy)
    changes=[]
    for match in selected_matches:
        incoming=text[match.start:match.end];replacement=_case_like(incoming,match.term.canonical)
        if match.action=='auto' and incoming!=replacement:
            changes.append(dict(source=incoming,replacement=replacement,start=match.start,end=match.end,
                rule=match.rule,confidence=round(match.confidence,6),canonical=match.term.canonical))
    output=text
    for change in reversed(changes):
        assert text[change['start']:change['end']]==change['source']
        output=output[:change['start']]+change['replacement']+output[change['end']:]
    return dict(text=output,controlled_text=text,changes=changes,blocked=obj.guard_audit,
        preserved_variants=obj.preserved,overlap_resolutions=obj.overlap_audit,
        identifier_protections=obj.identifier_spans,wall_ms=(time.perf_counter_ns()-started)/1_000_000,
        policy='Second laboratory revision only; no production integration')

"""Preserve identifier-associated phrases, including nested suffixes."""
from . import matching_policy as first

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

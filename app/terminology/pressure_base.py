"""Frozen direction signature used by the refined production guard."""
import re
from functools import lru_cache
from app.captions.terminology_normalizer import _source_tokens, _valid_span
from .lexical import edit_distance

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

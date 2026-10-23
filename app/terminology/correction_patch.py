"""Bounded, separately reversible spelling repair and same-word recognition.

Formatting variants supply terminology context only. They never rewrite RAW
or expand aliases/acronyms. Observed spelling repairs use a closed allowlist.
"""
from collections import defaultdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

from app.captions.terminology_normalizer import Correction, Suggestion, _case_like, _source_tokens

PATCH_VERSION = 'medical-corrections-v1'
HYPHENS = '-‐‑–—−'
BOUNDARY = r"[\w'’/\\" + re.escape(HYPHENS) + ']'
OBSERVED_REPAIR = ('primary adosterizm', 'primary aldosteronism')
REVIEW_ONLY = (('resisted hypertension', 'resistant hypertension'),
               ('resisted hyper tension', 'resistant hypertension'))


def lexical_key(text):
    return tuple(t.normalized for t in _source_tokens(text))


def same_word_pattern(canonical):
    tokens = _source_tokens(canonical)
    parts = []
    for index, token in enumerate(tokens):
        if index:
            gap = canonical[tokens[index - 1].end:token.start]
            if any(char in HYPHENS for char in gap):
                parts.append(r'(?:[ \t]*[' + re.escape(HYPHENS) + r'][ \t]*|[ \t]+)')
            elif gap.isspace():
                parts.append(r'[ \t]+')
            else:
                raise ValueError('Unsupported canonical punctuation')
        parts.append(re.escape(token.text))
    return re.compile(r'(?<!' + BOUNDARY + ')' + ''.join(parts) + r'(?!' + BOUNDARY + ')', re.I)


def literal_pattern(text):
    return re.compile(r'(?<!' + BOUNDARY + ')' + re.escape(text).replace(r'\ ',r'[ \t]+')
                      + r'(?!' + BOUNDARY + ')', re.I)


def identifier_context(text, start):
    clause = re.split(r'[,;:.!?\n]', text[:start])[-1]
    return any('_' in word for word in clause.split()[-3:])


def audit_catalog(concepts, forms):
    """Inspect every bilingual pair, including collisions with preserved forms."""
    indexes = {language:defaultdict(set) for language in ('en','es')}
    for c in concepts:
        for language in indexes:
            indexes[language][lexical_key(c[language])].add(c['id'])
    for form in forms:
        if form['language'] in indexes:
            indexes[form['language']][lexical_key(form['form'])].add(form['concept_id'])
    rows = []
    eligible = []
    for c in concepts:
        row = dict(concept_id=c['id'],en=c['en'],es=c['es'],asr_evaluated=c['asr_evaluated'],decisions={})
        for language in indexes:
            canonical = c[language]
            tokens = _source_tokens(canonical)
            reasons = []
            if not any(h in canonical for h in HYPHENS): reasons.append('no_hyphen_variant_needed')
            if len(tokens)<3: reasons.append('short_expression_kept_literal')
            if any(char.isdigit() for char in canonical): reasons.append('numeric_expression_kept_literal')
            if any(t.text.isupper() for t in tokens): reasons.append('acronym_or_symbol_kept_literal')
            if c['context_required']: reasons.append('contextual_review_required')
            collisions = indexes[language][lexical_key(canonical)] - {c['id']}
            if collisions: reasons.append('collision_with_another_concept_or_form')
            try:same_word_pattern(canonical)
            except ValueError:reasons.append('unsupported_punctuation_kept_literal')
            row['decisions'][language] = dict(
                action='same_words_context_only' if not reasons else 'keep_existing_policy',
                reasons=reasons,conflicting_concept_ids=sorted(collisions))
            if not reasons:eligible.append(dict(concept_id=c['id'],language=language))
        rows.append(row)
    collisions = [dict(language=language,words=list(key),concept_ids=sorted(ids))
                  for language,index in indexes.items() for key,ids in index.items() if len(ids)>1]
    return dict(concept_count=len(concepts),rows=rows,format_recognition=eligible,
                lexical_collisions=collisions,automatic_alias_expansion=False,
                global_tolerance_relaxation=False)


class CorrectionPatch:
    def __init__(self, directory, release):
        folder = Path(directory)
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if not isinstance(manifest,dict):raise ValueError('Invalid correction patch manifest')
        if manifest.get('policy')!='bounded_mvp' or manifest.get('version')!=PATCH_VERSION:
            raise ValueError('Invalid correction patch policy')
        members = manifest.get('files',[])
        if not isinstance(members,list) or len(members)!=1 or not isinstance(members[0],dict) or members[0].get('name')!='rules.json':
            raise ValueError('Invalid correction patch members')
        data = (folder/'rules.json').read_bytes()
        if len(data)>200_000 or len(data)!=members[0]['bytes'] or hashlib.sha256(data).hexdigest()!=members[0]['sha256']:
            raise ValueError('Correction patch integrity mismatch')
        rules = json.loads(data)
        if not isinstance(rules,dict):raise ValueError('Invalid correction patch rules')
        if rules.get('version')!=PATCH_VERSION or rules.get('base_version')!=release.version:
            raise ValueError('Correction patch version mismatch')
        if rules.get('observed_repairs')!=[dict(source=OBSERVED_REPAIR[0],target=OBSERVED_REPAIR[1])]:
            raise ValueError('Spelling repair is not on the closed allowlist')
        if rules.get('review_only')!=[dict(source=a,target=b) for a,b in REVIEW_ONLY]:
            raise ValueError('Invalid review-only forms')
        expected = audit_catalog(release.concepts,release.forms)['format_recognition']
        if rules.get('format_recognition')!=expected:
            raise ValueError('Unreviewed formatting or collision policy')
        by_name = defaultdict(list)
        self.by_id = {c['id']:c for c in release.concepts}
        for c in release.concepts:by_name[c['en']].append(c)
        for target in [OBSERVED_REPAIR[1],*[b for a,b in REVIEW_ONLY]]:
            if len(by_name[target])!=1 or by_name[target][0]['context_required']:
                raise ValueError('Missing or ambiguous repair target')
        self.version = PATCH_VERSION
        self.repair = (literal_pattern(OBSERVED_REPAIR[0]),OBSERVED_REPAIR[1])
        self.reviews = [(literal_pattern(a),b) for a,b in REVIEW_ONLY]
        self.formats = {language:[] for language in ('en','es')}
        for entry in expected:
            c=self.by_id[entry['concept_id']];language=entry['language']
            self.formats[language].append((c,same_word_pattern(c[language])))

    def scan(self,text,language):
        corrections=[];suggestions=[]
        if language!='en':return corrections,suggestions
        pattern,target=self.repair
        for match in pattern.finditer(text):
            if identifier_context(text,match.start()):continue
            corrections.append(Correction(match.group(),_case_like(match.group(),target),match.start(),match.end(),
                'medical_observed_spelling',1.0,target))
        for pattern,target in self.reviews:
            for match in pattern.finditer(text):
                if identifier_context(text,match.start()):continue
                # Zero is intentional: literal observation supplies no validated
                # semantic confidence for changing a valid English expression.
                suggestions.append(Suggestion(match.group(),target,match.start(),match.end(),
                    'medical_context_review_only',0.0))
        return corrections,suggestions

    def matches(self,text,language):
        hits=[]
        for c,pattern in self.formats.get(language,()):
            for match in pattern.finditer(text):
                if identifier_context(text,match.start()):continue
                hits.append(dict(concept=c,start=match.start(),end=match.end()))
        return hits

    def status(self):
        return dict(version=self.version,observed_repair_rules=1,review_only_forms=len(self.reviews),
                    format_recognition={lang:len(rows) for lang,rows in self.formats.items()})


@lru_cache(maxsize=4)
def load_patch(directory,release):
    return CorrectionPatch(directory,release)

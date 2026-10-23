"""Build a separate runtime release from frozen research; never edit evidence."""
import ast
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'research/hypertension_2026-10-20'
DEST=ROOT/'glossaries/releases/medical-657-v1'
CODE=ROOT/'app/terminology'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,text):
    if path.exists():raise ValueError('Immutable release/source already exists: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
def nodes(path,names):
    source=path.read_text(encoding='utf-8');result=[]
    for node in ast.parse(source).body:
        found=getattr(node,'name',None)
        if isinstance(node,ast.Assign):found=next((t.id for t in node.targets if isinstance(t,ast.Name)),None)
        if found in names:
            start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])
            result.append('\n'.join(source.splitlines()[start-1:node.end_lineno]))
    return '\n\n'.join(result)+'\n'

def main():
    global DEST
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version',default='medical-657-v1')
    parser.add_argument('--candidate',type=Path,default=BASE/'integration_candidate')
    parser.add_argument('--thresholds',type=Path,default=BASE/'remaining_terms_trial_37_v1/combined_thresholds.json')
    args=parser.parse_args()
    if not re.fullmatch(r'medical-657-v[1-9][0-9]*',args.version):
        parser.error('Use a new medical-657-vN release name')
    DEST=ROOT/'glossaries/releases'/args.version
    if DEST.exists():raise ValueError('Release already exists; use a new version')
    package=args.candidate.resolve()
    threshold_path=args.thresholds.resolve()
    if not package.is_relative_to(ROOT) or not threshold_path.is_relative_to(ROOT):
        parser.error('Reviewed inputs must be inside this workspace')
    for row in read(package/'manifest.json')['files']:
        p=package/row['name']
        assert p.stat().st_size==row['bytes'] and digest(p)==row['sha256']
    concepts=read(package/'concepts.json')['concepts']
    thresholds={r['concept_id']:r['selected_auto_threshold'] for r in read(threshold_path)['decisions']}
    forms=read(package/'form_decisions.json')['forms']
    bundle=dict(version=args.version,policy='soft_testing',concepts=[dict(id=c['id'],en=c['canonical_en'],es=c['preferred_es'],
        category=c['category'],source_ids=c['source_ids'],asr_evaluated=c['id'] in thresholds,
        fuzzy_threshold_en=thresholds.get(c['id']),context_required=next(e['reference_context_required'] for e in read(package/'normalization_en.json')['entries'] if e['concept_id']==c['id'])) for c in concepts],
        preservation_forms=[dict(form_id=f['form_id'],concept_id=f['concept_id'],language=f['language'],form=f['form'],bucket=f['bucket']) for f in forms],
        legacy_glossaries_untouched=True,automatic_alias_expansion=False,global_tolerance_relaxation=False)
    assert len(bundle['concepts'])==657 and len(thresholds)==97
    write(DEST/'bundle.json',json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    provenance=[package/'manifest.json',threshold_path,
                BASE/'polarity_flexible_trial_97_v1/visible_root_refinement_v2/pressure_refined.py']
    manifest=dict(version=bundle['version'],policy='soft_testing',concept_count=657,evaluated_english_concepts=97,
        active_english_fuzzy_terms=sum(v is not None for v in thresholds.values()),
        sources=[dict(path=str(p.relative_to(ROOT)).replace('\\','/'),sha256=digest(p)) for p in provenance],
        files=[dict(name='bundle.json',sha256=digest(DEST/'bundle.json'),bytes=(DEST/'bundle.json').stat().st_size)])
    write(DEST/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    if (CODE/'__init__.py').exists():
        print(json.dumps(dict(release=str(DEST),concepts=657,evaluated=97,fuzzy=80),ensure_ascii=False))
        return
    write(CODE/'__init__.py','"""Versioned medical terminology for reversible MVP trials."""\n')
    lexical=nodes(ROOT/'trad_lab/metrics.py',{'TOKEN','NEGATIONS','NUMBER_WORDS','UNITS','MEASUREMENT','tokens','measurement_signatures'})
    write(CODE/'lexical.py','"""Frozen lexical guards; no laboratory dependency at runtime."""\nimport re\nimport unicodedata\nfrom app.captions.terminology_normalizer import _edit_distance as edit_distance\n\n'+lexical)
    context=nodes(BASE/'context_boundary_trial_10_v1/evaluate_context.py',{'FUNCTION_WORDS','CONTRAST_GROUPS','ratio','quantity_signature','token_alignment','guard_span','ContextNormalizer','document'})
    write(CODE/'context_guards.py','"""Context rules promoted from the frozen laboratory; originals retained."""\nfrom collections import Counter\nfrom difflib import SequenceMatcher\nfrom functools import lru_cache\nfrom app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig, _tokens\nfrom .lexical import tokens, measurement_signatures, NEGATIONS, NUMBER_WORDS, UNITS\n\n'+context)
    policy=nodes(BASE/'lexical_controls_trial_60_v1/lab_normalizer.py',{'PROFILES','IRREGULAR','plural_spellings','number_changes','valid_outer_boundary','preservation_spans','contained_pattern','LaboratoryNormalizer'})
    write(CODE/'matching_policy.py','"""Conservative number, variant and overlap selection rules."""\nimport time\nfrom . import context_guards as ctx\nfrom app.captions.terminology_normalizer import _source_tokens, _tokens, _valid_span, _case_like\n\n'+policy)
    boundary=nodes(BASE/'lexical_controls_trial_60_v1/boundary_refinement_v2/boundary_normalizer.py',{'BoundaryNormalizer'})
    write(CODE/'boundary_policy.py','"""Preserve identifier-associated phrases, including nested suffixes."""\nfrom . import matching_policy as first\n\n'+boundary)
    pressure=nodes(BASE/'polarity_flexible_trial_97_v1/pressure_guard.py',{'PREFIXES','BASE_WORDS','EXACT','VISIBLE','direction_signature'})
    write(CODE/'pressure_base.py','"""Frozen direction signature used by the refined production guard."""\nimport re\nfrom functools import lru_cache\nfrom app.captions.terminology_normalizer import _source_tokens, _valid_span\nfrom .lexical import edit_distance\n\n'+pressure)
    refined=nodes(BASE/'polarity_flexible_trial_97_v1/visible_root_refinement_v2/pressure_refined.py',{'direction_signature','direction_verdict','PressureNormalizer','candidate'})
    # The original module's first.previous chain becomes an explicit local link.
    write(CODE/'guarded_matcher.py','"""Refined directional gate; runtime contains no research imports."""\nimport time\nfrom functools import lru_cache\nfrom . import pressure_base as first\nfrom . import boundary_policy as previous\nfrom app.captions.terminology_normalizer import _source_tokens, _case_like, _tokens\nfrom .lexical import edit_distance\n\nfirst.previous=previous\n\n'+refined)
    print(json.dumps(dict(release=str(DEST),concepts=657,evaluated=97,fuzzy=80),ensure_ascii=False))

if __name__=='__main__':main()

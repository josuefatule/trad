"""Build isolated research artifacts; never writes production paths or configuration."""
from __future__ import annotations
import collections
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from app.captions.terminology_normalizer import TerminologyNormalizer, NormalizerConfig, _tokens
from trad_lab.glossary import audit

EXPECTED_HASH = '4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896'
SOURCE_PATH = ROOT / 'glossaries' / 'medical_base_en.json'
START = dt.datetime.fromisoformat('2026-10-20T20:08:31+00:00')

def save(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def forms_key(value):
    return ' '.join(_tokens(value))

def read_rows(name):
    group = None
    for number, line in enumerate((HERE / name).read_text(encoding='utf-8').splitlines(), 1):
        if not line or line.startswith('#'):
            continue
        if line.startswith('@'):
            category, ids, locator, support = line[1:].split('|')
            group = dict(category=category, source_ids=ids.split(','), locator=locator, support=support)
            continue
        values = line.split('|')
        assert len(values) == 5, (name, number, values)
        en, es, en_forms, es_forms, note = values
        assert group is not None
        yield dict(group, en=en, es=es, aliases_en=[s for s in en_forms.split(';') if s],
                   variants_es=[s for s in es_forms.split(';') if s], note=note,
                   curation_file=name, curation_line=number)

# Count conceptual/grammatical variants once in the research dataset. The
# operational candidate retains original canonicals to preserve compatibility.
MERGES = {
    'high blood pressure': 'hypertension',
    'arterial hypertension': 'hypertension',
    'hypertensive': 'hypertension',
    'normotensive': 'normotension',
    'systolic pressure': 'systolic blood pressure',
    'diastolic pressure': 'diastolic blood pressure',
    'cardiovascular disease risk': 'cardiovascular risk',
    'lifestyle management': 'lifestyle modification',
    'plasma levels': 'plasma concentration',
    'peripheral vascular resistance': 'systemic vascular resistance',
}

AMBIGUITIES = {
    'PA': ['primary aldosteronism (EN)', 'presión arterial (ES)', 'pulmonary artery (EN)'],
    'MRA': ['mineralocorticoid receptor antagonist', 'magnetic resonance angiography'],
    'MRAs': ['mineralocorticoid receptor antagonists', 'plural de angiografía por RM en algunos discursos'],
    'MR': ['mineralocorticoid receptor', 'magnetic resonance', 'mitral regurgitation'],
    'RAS': ['renin-angiotensin system', 'renal artery stenosis', 'RAS gene family'],
    'MAP': ['mean arterial pressure', 'palabra inglesa map'],
    'PAC': ['plasma aldosterone concentration', 'premature atrial contraction'],
    'PRA': ['plasma renin activity', 'panel-reactive antibody'],
    'APA': ['aldosterone-producing adenoma', 'sigla de varias sociedades'],
    'HR': ['heart rate', 'hazard ratio'],
    'HRV': ['heart rate variability (EN)', 'hipertensión renovascular (ES en S29)'],
    'ECA': ['enzima convertidora de angiotensina', 'ensayo controlado aleatorizado'],
    'RAR': ['ratio aldosterona-renina', 'reducción absoluta del riesgo'],
    'IC': ['intervalo de confianza', 'insuficiencia cardíaca'],
    'CO': ['cardiac output', 'carbon monoxide'],
    'NO': ['nitric oxide', 'negación'],
    'PCR': ['protein-to-creatinine ratio', 'polymerase chain reaction', 'proteína C reactiva'],
    'ACS': ['autonomous cortisol secretion', 'acute coronary syndrome'],
    'AF': ['atrial fibrillation', 'otras abreviaturas según especialidad'],
    'MI': ['myocardial infarction', 'mitral insufficiency'],
    'ACE': ['angiotensin-converting enzyme', 'adverse childhood experiences'],
}

# Only aliases with concrete semantic ambiguity or demonstrated grammatical
# corruption are removed, in the separate candidate. Thresholds are untouched.
BLOCKED_ALIASES = {'PA', 'MRA', 'MRAs', 'MR', 'RAS', 'MAP', 'PAC', 'PRA', 'APA',
                   'frail patients', 'diuretic therapy', 'Eighth Joint National Committee'}

CONFUSABLE = {
    'hypertension': ['pulmonary hypertension', 'elevated blood pressure', 'hypotension'],
    'primary aldosteronism': ['hyperaldosteronism', 'secondary aldosteronism'],
    'resistant hypertension': ['refractory hypertension', 'uncontrolled hypertension', 'apparent treatment-resistant hypertension'],
    'nocturnal hypertension': ['non-dipping pattern'],
    'white-coat hypertension': ['white-coat effect'],
    'masked hypertension': ['masked uncontrolled hypertension'],
    'hypertensive emergency': ['hypertensive urgency', 'severe hypertension'],
    'hypokalemia': ['hyperkalemia', 'hypocalcemia'],
    'albuminuria': ['proteinuria'],
    'renal insufficiency': ['chronic kidney disease', 'kidney failure'],
    'hazard ratio': ['relative risk', 'odds ratio'],
    'preeclampsia': ['eclampsia', 'gestational hypertension'],
    'fetal growth restriction': ['small for gestational age'],
    'renal denervation': ['renal revascularization'],
    'mineralocorticoid receptor antagonists': ['magnetic resonance angiography', 'aldosterone synthase inhibitor'],
    'angiotensin II': ['angiotensin I', 'angiotensin-(1–7)'],
    'left ventricular ejection fraction': ['ejection fraction'],
    'salt intake': ['dietary sodium restriction'],
    'serious adverse events': ['severe adverse events'],
    'medication adherence': ['treatment persistence'],
    'natriuresis': ['diuresis'],
    'thiazide diuretics': ['thiazide-like diuretics'],
    'single-pill combination': ['polypill', 'fixed-dose combination'],
}

# Explicit cross-checks against Spanish and English texts actually consulted.
# Other translations remain proposals, even when medically familiar.
CROSSCHECKS = {
    'blood pressure': ['S02','S06'], 'hypertension': ['S02','S06'],
    'primary hypertension': ['S17','S29'], 'secondary hypertension': ['S09','S29'],
    'systolic blood pressure': ['S08','S29'], 'diastolic blood pressure': ['S08','S29'],
    'mean arterial pressure': ['S04','S29'], 'pulse pressure': ['S08','S29'],
    'elevated blood pressure': ['S02','S32'], 'stage 1 hypertension': ['S02','S32'],
    'stage 2 hypertension': ['S02','S32'], 'primary aldosteronism': ['S10','S30'],
    'renin': ['S17','S30'], 'aldosterone': ['S10','S30'],
    'plasma renin activity': ['S10','S30'], 'aldosterone-to-renin ratio': ['S10','S30'],
    'angiotensin-converting enzyme inhibitors': ['S07','S32'],
    'angiotensin II receptor blockers': ['S07','S32'],
    'calcium channel blockers': ['S07','S32'], 'beta blockers': ['S07','S32'],
    'alpha blockers': ['S07','S32'], 'diuretics': ['S07','S32'],
    'chlorthalidone': ['S21','S33'], 'angiotensin II': ['S17','S32'],
    'orthostatic hypotension': ['S26','S31'], 'adrenal gland': ['S10','S30'],
    'secondary aldosteronism': ['S17','S30'], 'hyperaldosteronism': ['S10','S31'],
    'endothelial dysfunction': ['S17','S29'], 'renal ischemia': ['S17','S29'],
    'renal artery stenosis': ['S16','S29'], 'fibromuscular dysplasia': ['S16','S29'],
    'chronic kidney disease': ['S05','S29'], 'albuminuria': ['S05','S29'],
    'proteinuria': ['S05','S29'], 'acute kidney injury': ['S05','S29'],
    'magnetic resonance angiography': ['S16','S29'],
    'urine albumin-to-creatinine ratio': ['S05','S29'],
    'gestational hypertension': ['S13','S29'], 'preeclampsia': ['S12','S29'],
    'eclampsia': ['S47','S39'],
    'small for gestational age': ['S47','S51'], 'placental abruption': ['S47','S29'],
    'postpartum hypertension': ['S12','S29'],
    'mineralocorticoid receptor antagonists': ['S09','S29'],
    'continuous positive airway pressure': ['S27','S29'],
    'obstructive sleep apnea': ['S27','S29'], 'polysomnography': ['S27','S29'],
    'supine hypertension': ['S52'], 'magnesium sulfate': ['S55'],
    'cardiac output': ['S63','S64'], 'stroke volume': ['S63','S64'],
}

CATEGORY_CONTEXT = {
    'classification': 'Nombrar sociedad, año, estado de tratamiento y método de medición cuando definan el fenotipo.',
    'measurement': 'Distinguir procedimiento, dispositivo, muestra temporal y valor medido; no intercambiar técnicas ni umbrales.',
    'endocrine_renal': 'Interpretación dependiente de muestra, método analítico, fármacos, potasio y contexto endocrinológico.',
    'kidney': 'Distinguir agudo/crónico, estimado/medido, albúmina/proteína y la unidad de laboratorio.',
    'physiology': 'Mecanismo o estructura; no convertir asociación fisiológica en diagnóstico causal individual.',
    'medications': 'Nombre genérico; no equiparar dosis, sales, formulaciones, indicaciones o disponibilidad regulatoria.',
    'treatment': 'Terminología de estrategia terapéutica; no constituye pauta ni aprobación para integración.',
    'emergencies': 'Conservar negación, calificadores agudo/grave y presencia o ausencia de daño orgánico.',
    'pregnancy': 'Distinguir hipertensión crónica, gestacional y preeclampsia; respetar población y marco obstétrico.',
    'organ_damage': 'Conservar órgano, lateralidad, fase aguda/crónica y diferencia entre estructura, función y síndrome.',
    'risk_prevention': 'No convertir factor de riesgo, asociación o exposición en diagnóstico individual.',
    'lifestyle': 'Distinguir conducta, intervención y nutrientes; sal, sodio y potasio no son intercambiables.',
    'special_populations': 'Edad, embarazo, trasplante, fragilidad y disautonomía modifican la interpretación.',
    'clinical_trials': 'Nombre propio del estudio; conservar acrónimo, sufijo, población y componente investigado.',
    'research_methods': 'Conservar diseño, estimando, denominador, horizonte temporal y calificadores de desenlace.',
    'guidelines': 'Conservar año y organización; una guía histórica sigue siendo un término válido en una cita.',
    'units_measurement': 'No realizar conversiones numéricas, corregir dosis ni expandir unidades ambiguas automáticamente.',
    'conference_language': 'Lenguaje de conferencia; muchas unidades son expresiones léxicas, no enfermedades independientes.',
}

NAMED_ABBREVIATIONS = {
    'SPRINT trial': ('SPRINT','Systolic Blood Pressure Intervention Trial',['S18']),
    'ACCORD trial': ('ACCORD','Action to Control Cardiovascular Risk in Diabetes',['S46']),
    'REGARDS study': ('REGARDS','Reasons for Geographic and Racial Differences in Stroke',['S59']),
    'NHANES': ('NHANES','National Health and Nutrition Examination Survey',['S60']),
    'ALLHAT trial': ('ALLHAT','Antihypertensive and Lipid-Lowering Treatment to Prevent Heart Attack',['S19']),
    'CHAP trial': ('CHAP','Chronic Hypertension and Pregnancy',['S13','S47']),
    'PREVENT equations': ('PREVENT','Predicting Risk of cardiovascular disease EVENTs',['S03']),
    'SCORE2': ('SCORE2','Systematic COronary Risk Evaluation 2',['S29']),
}

def main():
    original_bytes = SOURCE_PATH.read_bytes()
    assert hashlib.sha256(original_bytes).hexdigest() == EXPECTED_HASH, 'Original changed; stop and audit before rebuilding.'
    original = json.loads(original_bytes.decode('utf-8-sig'))
    original_by_en = {t['canonical']: t for t in original['terms']}
    sources = json.loads((HERE/'sources.json').read_text(encoding='utf-8'))
    source_ids = {s['id'] for s in sources}
    rows = list(read_rows('original_terms_review.txt')) + list(read_rows('new_terms_review.txt'))
    updates = json.loads((HERE/'evidence_updates.json').read_text(encoding='utf-8'))
    for row in rows:
        if row['en'] in updates:
            row.update(updates[row['en']])
    assert len({r['en'] for r in rows}) == len(rows), 'Duplicate curated English canonical.'
    missing = sorted(set(original_by_en) - {r['en'] for r in rows})
    assert not missing, ('Missing original entries', missing)
    for row in rows:
        assert set(row['source_ids']) <= source_ids, row
    by_en = {r['en']: r for r in rows}
    assert set(MERGES.values()) <= set(by_en)
    concepts = []
    for row in rows:
        if row['en'] in MERGES:
            continue
        en = row['en']
        grouped = [row] + [r for r in rows if MERGES.get(r['en']) == en]
        original_entries = [copy.deepcopy(original_by_en[r['en']]) for r in grouped if r['en'] in original_by_en]
        aliases = []
        for r in grouped:
            aliases.extend(r['aliases_en'])
            old = original_by_en.get(r['en'], {})
            aliases.extend(old.get('aliases', []))
            aliases.extend(old.get('variants', []))
        aliases = list(dict.fromkeys(a for a in aliases if a != en))
        spanish_variants = list(dict.fromkeys(v for r in grouped for v in [r['es'], *r['variants_es']] if v != row['es']))
        abbreviations = []
        for lang, values in [('en', aliases), ('es', spanish_variants)]:
            for value in values:
                if re.fullmatch(r'[A-Z][A-Za-z0-9-]{0,10}', value) and any(c.isupper() for c in value):
                    abbreviations.append({'form':value, 'language':lang,
                                          'expansion':en if lang=='en' else row['es'],
                                          'other_meanings':AMBIGUITIES.get(value, []),
                                          'automatic_expansion_approved':False})
        if en in NAMED_ABBREVIATIONS:
            form, expansion, expansion_sources = NAMED_ABBREVIATIONS[en]
            abbreviations.append({'form':form,'language':'en','expansion':expansion,
                                  'source_ids':expansion_sources,'other_meanings':[],
                                  'automatic_expansion_approved':False})
        supported = row['support'] == 'supported'
        term_sources = list(dict.fromkeys([s for r in grouped for s in r['source_ids']] + CROSSCHECKS.get(en, [])))
        concept = {
            'id':'HTN_' + hashlib.sha256(en.encode('utf-8')).hexdigest()[:12],
            'canonical_en': en, 'preferred_es':row['es'], 'aliases_en':aliases,
            'variants_es':spanish_variants, 'abbreviations':abbreviations,
            'alias_review_status':'Research inventory, including inherited forms; not all are verified strict synonyms.',
            'form_reviews':[{'form':a,'language':'en',
                             'status':'rejected_for_context_free_substitution' if a in BLOCKED_ALIASES else 'source_and_context_review_required',
                             'automatic_substitution_approved':False} for a in aliases],
            'category':row['category'], 'scope':'systemic_arterial_hypertension_and_related_conference_vocabulary',
            'origin':'original' if original_entries else 'new_research_candidate',
            'original_entries':original_entries,
            'grouped_lexical_forms':[r['en'] for r in grouped],
            'grouped_lexical_forms_are_automatic_aliases':False,
            'clinical_context':CATEGORY_CONTEXT[row['category']],
            'notes':[r['note'] for r in grouped if r['note']],
            'evidence':[{'source_id':s, 'locator':r['locator'],
                         'supports':'concept_or_specialty_context; not automatically every alias or translation'}
                        for r in grouped for s in r['source_ids']],
            'source_ids':term_sources,
            'review':{
                'concept_status':'literature_supported_research_candidate' if supported else 'pending_targeted_source_verification',
                'translation_status':'crosschecked_in_en_and_es_sources' if en in CROSSCHECKS else 'proposed_translation_pending_individual_source_check',
                'translation_crosscheck_source_ids':CROSSCHECKS.get(en, []),
                'translation_crosscheck_method':'Comparison of terminology in consulted English and Spanish sources; no independent clinician certification.',
                'independent_clinician_review':'not_performed',
                'operational_status':'manual_review_required_not_approved',
                'evidence_limit':'Source support is not independent clinical certification or proof of ASR benefit.',
            },
            'ambiguity':{
                'risk':'high' if (en in CONFUSABLE or any(a.get('other_meanings') for a in abbreviations)
                                  or row['category'] in ('pregnancy','medications','emergencies','units_measurement')) else 'context_dependent',
                'confusable_with':CONFUSABLE.get(en, []),
                'automatic_substitution_approved':False,
            },
            'curation_provenance':[{'file':r['curation_file'],'line':r['curation_line']} for r in grouped],
        }
        concepts.append(concept)
    assert len({c['id'] for c in concepts}) == len(concepts)
    assert len({forms_key(c['canonical_en']) for c in concepts}) == len(concepts)

    candidate = copy.deepcopy(original)
    candidate['name'] = 'medical_base_en_extended_candidate'
    changes = []
    for item in candidate['terms']:
        if 'aliases' in item:
            removed = [a for a in item['aliases'] if a in BLOCKED_ALIASES]
            if removed:
                item['aliases'] = [a for a in item['aliases'] if a not in BLOCKED_ALIASES]
                if not item['aliases']:
                    del item['aliases']
                changes.append({'canonical':item['canonical'],'change':'remove_unsafe_aliases_in_candidate_only',
                                'removed_aliases':removed,'thresholds_unchanged':True,
                                'reason':'Context-blind expansion, incorrect title, or demonstrated grammatical corruption.'})
    added = []
    held = []
    for row in rows:
        if row['en'] in original_by_en or row['en'] in MERGES:
            continue
        if row['support'] != 'supported':
            held.append(row['en'])
            continue
        # Intentionally do not export research aliases or Spanish forms into
        # the English normalizer. Suggest never applies lexical corrections.
        candidate['terms'].append({'canonical':row['en'],'auto_apply':'suggest'})
        added.append(row['en'])
    assert set(candidate) == set(original)
    assert candidate['version'] == original['version']
    allowed={'canonical','aliases','variants','auto_apply','auto_threshold','suggest_threshold'}
    assert all(set(t) <= allowed for t in candidate['terms'])
    assert all(t.get('auto_apply') == 'suggest' for t in candidate['terms'][len(original['terms']):])
    for old,new in zip(original['terms'], candidate['terms']):
        for k in ('canonical','auto_apply','auto_threshold','suggest_threshold','variants'):
            assert old.get(k) == new.get(k), (old['canonical'],k)
    save('medical_base_en_extended_candidate.json', candidate)
    normalizer=TerminologyNormalizer.from_documents([candidate], NormalizerConfig())
    baseline=TerminologyNormalizer.from_documents([original], NormalizerConfig())
    audit_result=audit(str(SOURCE_PATH))
    save('original_glossary_audit.json',audit_result)

    samples=[
        'The PA pressure was measured.', 'Review the MRA of the renal arteries.',
        'A RAS mutation was detected.', 'Follow the MAP on the screen.',
        'The PAC burden increased.', 'These frail patients need follow-up.',
        'Serum potassium was 4.2 mg/dL.', 'The dose was 5 mg/day.',
        'Both hypokalemia and hyperkalemia were assessed.',
        'No pulmonary hypertension was diagnosed.',
        'No preeclampsia or eclampsia was detected.',
        'Renal denervation is different from renal revascularization.',
        'The fetal growth restriction and small for gestational age groups differed.',
        'The hazard ratio was 0.79 with a 95% confidence interval.',
        'The adrenal venous sampling was deferred.',
        'The dose was 5 micrograms per day and not 5 milligrams per day.',
        'We compared angiotensin I and angiotensin II.',
        'This patient does not have resistant hypertension.',
        'The BP was recorded after 5 minutes.',
    ]
    adversarial=[]
    for index, sample in enumerate(samples):
        before=baseline.normalize('baseline-'+str(index),sample)
        after=normalizer.normalize('candidate-'+str(index),sample)
        adversarial.append({'input':sample,'original_output':before.normalized_text,
                            'candidate_output':after.normalized_text,
                            'candidate_lexical_changes':[
                                {'source':c.source,'replacement':c.replacement,'rule':c.rule}
                                for c in after.corrections if c.rule!='deterministic_spacing'],
                            'candidate_suggestion_count':len(after.suggestions),
                            'assessment':'unchanged' if after.normalized_text==sample else 'inherited_rule_or_unresolved_review_required'})
    assert all(x['candidate_output']==x['input'] for x in adversarial[:6]), 'Proven unsafe aliases still apply.'
    new_only={'name':'new_suggest_only','version':candidate['version'],'terms':candidate['terms'][len(original['terms']):]}
    new_normalizer=TerminologyNormalizer.from_documents([new_only],NormalizerConfig())
    new_check_samples=[*samples,'adrenal venous sampleing','micro vascular remodeling','aldosteron synthase inhibitor']
    new_only_checks=[]
    for i,sample in enumerate(new_check_samples):
        result=new_normalizer.normalize('new-'+str(i),sample)
        assert result.normalized_text==sample, (sample,result.normalized_text)
        assert not result.corrections
        new_only_checks.append({'input':sample,'unchanged':True,'suggestion_count':len(result.suggestions)})

    # Exact collision audit must match the real runtime tokenizer.
    alias_map=collections.defaultdict(set)
    for c in concepts:
        for form in [c['canonical_en'],*c['aliases_en']]:
            alias_map[forms_key(form)].add(c['canonical_en'])
    research_collisions=[{'normalized_form':f,'concepts':sorted(v)} for f,v in alias_map.items() if len(v)>1]
    counts={
        'original_operational_entries':len(original['terms']),
        'curated_lexical_rows':len(rows), 'research_concept_records':len(concepts),
        'explicitly_grouped_extra_lexical_rows':len(rows)-len(concepts),
        'literature_supported_research_candidates':sum(c['review']['concept_status']=='literature_supported_research_candidate' for c in concepts),
        'pending_targeted_source_verification':sum(c['review']['concept_status']=='pending_targeted_source_verification' for c in concepts),
        'translations_crosschecked_in_external_en_es_sources':len(CROSSCHECKS),
        'translations_pending_individual_source_check':len(concepts)-len(CROSSCHECKS),
        'independently_clinician_validated_concepts':0,
        'new_operational_suggest_only_entries':len(added),
        'held_new_lexical_rows':len(held),
        'candidate_operational_entries':len(candidate['terms']),
        'removed_unsafe_aliases':sum(len(c['removed_aliases']) for c in changes),
        'research_alias_collisions':len(research_collisions),
        'original_exact_form_collisions':len(audit_result['exact_collisions']),
        'original_fuzzy_canonical_screening_pairs':len(audit_result['fuzzy_canonical_screening']),
        'consulted_sources':len(sources),
    }
    validation={
        'counts':counts,'json_syntax':'pass', 'schema_runtime_loader':'pass',
        'original_sha256_before':EXPECTED_HASH,
        'original_sha256_after':hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest(),
        'original_unchanged':hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()==EXPECTED_HASH,
        'original_thresholds_and_policies_unchanged_in_candidate':True,
        'original_294_canonicals_retained_in_candidate':True,
        'new_entries_automatic_replacement':'disabled_suggest_only',
        'new_entries_operational_aliases_or_variants_added':False,
        'schema_extra_operational_fields':[], 'research_alias_collisions':research_collisions,
        'candidate_changes_to_original_entries':changes,
        'held_new_terms':held,'adversarial_cases':adversarial,'new_only_cases':new_only_checks,
        'limitations':[
            'No actual conference audio benchmark, ASR improvement, latency or translation quality measurement was performed.',
            'The candidate retains original exact/fuzzy policies. Removal of demonstrated unsafe aliases does not certify the remaining baseline rules.',
            'Research concept support does not attest every alias, full English wording, or proposed Spanish translation.',
            'No independent clinician or terminologist reviewed the dataset.',
            'Suggest-only entries can still generate lexical fuzzy suggestions; these are not evidence of medical equivalence and must not be auto-applied by downstream consumers.',
        ],
    }
    save('validation_results.json',validation)
    now=dt.datetime.now(dt.timezone.utc)
    local=now.astimezone(dt.timezone(dt.timedelta(hours=-4)))
    dataset={
        'name':'TRAD hypertension research EN-ES', 'schema_version':'1.0.0',
        'updated_at':local.isoformat(timespec='seconds'), 'research_date':'2026-10-20',
        'status':'documented_research_batch_requires_further_verification',
        'original':{'path':str(SOURCE_PATH),'sha256':EXPECTED_HASH,'entries':len(original['terms'])},
        'counting_policy':'One canonical research record per curated conceptual/lexical unit after explicit synonym and adjective grouping; conference expressions and subtypes remain separately labeled. This is not a claim of 600-1000 fully verified bilingual concepts.',
        'counts':counts,'sources':sources,'concepts':concepts,
        'do_not_merge':CONFUSABLE,
        'cross_language_abbreviation_ambiguities':AMBIGUITIES,
        'rejected_equivalences':[
            {'a':'systemic arterial hypertension','b':'pulmonary hypertension','reason':'Different circulations and diseases.','sources':['S37']},
            {'a':'primary aldosteronism','b':'all hyperaldosteronism','reason':'Primary subtype is not the entire category.','sources':['S10','S30','S31']},
            {'a':'hypertensive emergency','b':'severe hypertension without acute organ damage','reason':'Acute organ damage changes the clinical entity.','sources':['S15','S29']},
            {'a':'hazard ratio','b':'risk ratio or odds ratio','reason':'Different effect measures; translation cannot collapse them.','sources':['S18','S20']},
            {'a':'fetal growth restriction','b':'small for gestational age','reason':'Clinical growth disorder and size classification are not identical.','sources':['S13','S29']},
        ],
        'scope_reference_entities':[{'canonical_en':'pulmonary hypertension','preferred_es':'hipertensión pulmonar','status':'scope_boundary_only_not_counted_as_systemic_hypertension','source_ids':['S37']}],
        'operational_export':{'filename':'medical_base_en_extended_candidate.json','integrated':False,
                              'candidate_only':True,'new_entries_policy':'suggest','new_aliases_exported':False,
                              'changes_to_original_entries':changes},
    }
    save('hypertension_research_en_es.json',dataset)
    progress={
        'updated_at':local.isoformat(timespec='seconds'), 'started_at_utc':START.isoformat(),
        'checkpoint_at_utc':now.isoformat(timespec='seconds'),
        'observed_wall_clock_minutes':round((now-START).total_seconds()/60,2),
        'effective_research_hours_measured':None,
        'time_accounting':'Wall-clock interval includes curation and validation; not a measurement of active research time. Three effective hours have not been achieved or claimed.',
        'requested_effective_work_hours':3,'status':'partial_research_batch_delivered_no_background_work',
        'counts':counts,'cycles_completed':[
            {'cycle':'A','work':'Original schema, tokenizer, loading, duplicates and runtime integration audited.'},
            {'cycle':'B1','work':'Current general guidelines, measurement, classification and bilingual official sources consulted.'},
            {'cycle':'C1','work':'Detected acronym collisions, disease distinctions and source-access limitations.'},
            {'cycle':'D1','work':'Consulted NLM Spanish, SEC translation and Endocrine Society 2025 to address ambiguity.'},
            {'cycle':'B2','work':'Curated renal, endocrine, physiology, drugs, pregnancy, organ damage and trial vocabulary.'},
            {'cycle':'C2','work':'Grouped lexical duplicates, separated translation verification and retained source limitations.'},
            {'cycle':'D2','work':'Reproduced unsafe baseline substitutions and removed those aliases only in candidate.'},
            {'cycle':'V1','work':'Parsed JSON, loaded actual normalizer and ran adversarial text checks.'},
        ],
        'category_counts':dict(collections.Counter(c['category'] for c in concepts)),
        'categories_initial_pass_completed':sorted(set(c['category'] for c in concepts)),
        'categories_fully_verified':[],
        'categories_pending':dict(collections.Counter(c['category'] for c in concepts if c['review']['concept_status'].startswith('pending'))),
        'pending_concept_ids':[c['id'] for c in concepts if c['review']['concept_status'].startswith('pending')],
        'pending_translation_ids':[c['id'] for c in concepts if c['review']['translation_status'].startswith('proposed')],
        'original_sha256':EXPECTED_HASH,'original_modified':False,
        'sources_used':[{'id':s['id'],'url':s['url'],'access_level':s['access_level']} for s in sources],
        'open_questions':[
            'Complete term-by-term Spanish source verification and independent clinician/terminologist review.',
            'Confirm primary sources for pending original conference and trial names, and new held candidates.',
            'Review 2025 ESC pregnancy guideline and relevant 2026 cardiorenal documents before claiming exhaustive currency in subspecialties.',
            'Read original full texts/corrigenda where only indexed excerpts or abstracts were accessible.',
            'Check precision, recall, negation, numbers, dosage, units and latency on representative conference audio in an isolated environment.',
            'Review retained original fuzzy policies and aliases that were not changed in this batch.',
        ],
        'next_research_line':'Start with pending IDs and untranslated-source checks; prioritize obstetrics 2025, endocrine confirmation tests, investigational drugs and baseline acronym safety. Do not re-count lexical variants as new concepts.',
        'deep_research_connector':'not_available_in_exposed_tools_or_plugin_search',
        'continuity_files':['sources.json','original_terms_review.txt','new_terms_review.txt','validation_results.json','build_research.py'],
        'background_work':False,'scheduled_automation':False,'commits_created':False,'integration_performed':False,
    }
    save('hypertension_research_progress.json',progress)
    print(json.dumps({'counts':counts,'wall_clock_minutes':progress['observed_wall_clock_minutes'],
                      'candidate_changes':changes,'research_collisions':research_collisions},ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()

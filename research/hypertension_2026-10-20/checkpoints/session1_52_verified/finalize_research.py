"""Validate and package the delivered research batch, without changing TRAD."""
from __future__ import annotations
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import zipfile

HERE=Path(__file__).resolve().parent

def read(name):
    return json.loads((HERE/name).read_text(encoding='utf-8'))

def write_json(name, value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    data=read('hypertension_research_en_es.json')
    validation=read('validation_results.json')
    candidate=read('medical_base_en_extended_candidate.json')
    progress=read('hypertension_research_progress.json')
    sources=read('sources.json')
    counts=data['counts']
    concepts=data['concepts']
    source_ids={s['id'] for s in sources}
    assert len(source_ids)==len(sources)
    assert data['sources']==sources
    assert counts==validation['counts']==progress['counts']
    assert len(concepts)==counts['research_concept_records']
    assert len({c['canonical_en'].casefold() for c in concepts})==len(concepts)
    assert len({c['id'] for c in concepts})==len(concepts)
    assert all(c['canonical_en'] and c['preferred_es'] for c in concepts)
    assert all(set(c['source_ids'])<=source_ids for c in concepts)
    assert all(set(c['review']['translation_crosscheck_source_ids'])<=source_ids for c in concepts)
    assert all(e['source_id'] in source_ids for c in concepts for e in c['evidence'])
    assert all(not c['ambiguity']['automatic_substitution_approved'] for c in concepts)
    assert counts['translations_crosschecked_in_external_en_es_sources']==sum(
        c['review']['translation_status']=='crosschecked_in_en_and_es_sources' for c in concepts)
    assert set(candidate)=={'name','version','terms'}
    assert len(candidate['terms'])==counts['candidate_operational_entries']
    assert all(t['auto_apply']=='suggest' and set(t)=={'canonical','auto_apply'}
               for t in candidate['terms'][counts['original_operational_entries']:])
    assert all(re.match(r'^https?://',s['url']) for s in sources)
    actual_original_hash=hashlib.sha256(Path(data['original']['path']).read_bytes()).hexdigest()
    assert actual_original_hash==data['original']['sha256']==validation['original_sha256_before']
    assert not data['operational_export']['integrated']
    now=dt.datetime.now(dt.timezone.utc)
    local=now.astimezone(dt.timezone(dt.timedelta(hours=-4)))
    start=dt.datetime.fromisoformat(progress['started_at_utc'])
    progress.update(updated_at=local.isoformat(timespec='seconds'),
                    checkpoint_at_utc=now.isoformat(timespec='seconds'),
                    observed_wall_clock_minutes=round((now-start).total_seconds()/60,2),
                    final_artifact_integrity_checks='pass',
                    final_original_sha256=actual_original_hash)
    progress['cycles_completed'].append({'cycle':'D3','work':'Targeted external checks for physiology, obstetric terminology, confirmation tests and alternate acronym meanings; unresolved proposals remain flagged.'})
    progress['cycles_completed'].append({'cycle':'V2','work':'Final cross-file integrity checks, source-reference checks, hashes and archive verification.'})
    progress['open_questions']=[s.replace('Review 2025 ESC pregnancy guideline','Read complete 2025 ESC pregnancy guideline') for s in progress['open_questions']]
    write_json('hypertension_research_progress.json',progress)
    validation['final_artifact_integrity_checks']={
        'all_json_files_parse':True,'cross_file_counts_match':True,
        'source_reference_ids_exist':True,'stable_concept_ids_unique':True,
        'translations_count_consistent':True,'no_new_automatic_corrections_enabled':True,
        'original_hash_final':actual_original_hash,
        'finalized_at':local.isoformat(timespec='seconds'),
    }
    write_json('validation_results.json',validation)

    labels={
        'original_operational_entries':'Entradas originales',
        'curated_lexical_rows':'Formas léxicas curadas',
        'research_concept_records':'Registros de investigación tras agrupación',
        'literature_supported_research_candidates':'Candidatos con respaldo conceptual o temático',
        'pending_targeted_source_verification':'Registros con fuente puntual pendiente',
        'translations_crosschecked_in_external_en_es_sources':'Equivalencias cotejadas en fuentes EN y ES',
        'translations_pending_individual_source_check':'Traducciones propuestas pendientes de cotejo individual',
        'independently_clinician_validated_concepts':'Registros con validación clínica independiente',
        'new_operational_suggest_only_entries':'Términos operacionales nuevos de solo sugerencia',
        'held_new_lexical_rows':'Propuestas nuevas retenidas fuera del candidato',
        'candidate_operational_entries':'Entradas del candidato operacional',
        'consulted_sources':'Fuentes seleccionadas en el catálogo',
    }
    summary='| Medida | Cantidad |\n|---|---:|\n'+'\n'.join(f'| {label} | {counts[k]} |' for k,label in labels.items())
    category_labels={
        'classification':'Clasificación y fenotipos','measurement':'Medición y monitorización',
        'guidelines':'Guías y sociedades','conference_language':'Lenguaje de congreso',
        'risk_prevention':'Riesgo y prevención','research_methods':'Métodos de investigación',
        'clinical_trials':'Ensayos, cohortes y encuestas','endocrine_renal':'Endocrinología y mecanismos renales',
        'kidney':'Nefrología','treatment':'Tratamientos y estrategias',
        'medications':'Fármacos y clases','organ_damage':'Daño orgánico y enfermedad cardiovascular',
        'lifestyle':'Estilo de vida','units_measurement':'Unidades y vocabulario de medición',
        'physiology':'Fisiología y fisiopatología','emergencies':'Emergencias y daño agudo',
        'pregnancy':'Embarazo','special_populations':'Poblaciones especiales',
    }
    categories='| Categoría | Registros | Fuente puntual pendiente |\n|---|---:|---:|\n'
    for category,total in Counter(c['category'] for c in concepts).items():
        pending=sum(c['category']==category and c['review']['concept_status'].startswith('pending') for c in concepts)
        categories+=f'| {category_labels[category]} | {total} | {pending} |\n'
    removed='| Entrada | Alias retirados del candidato |\n|---|---|\n'+'\n'.join(
        f"| {c['canonical']} | {', '.join(c['removed_aliases'])} |" for c in validation['candidate_changes_to_original_entries'])
    adversarial='| Entrada de prueba | Salida con original | Salida con candidato |\n|---|---|---|\n'+'\n'.join(
        f"| {c['input']} | {c['original_output']} | {c['candidate_output']} |" for c in validation['adversarial_cases'][:6])
    pending='\n'.join('- '+c['canonical_en']+' ('+c['id']+')' for c in concepts if c['review']['concept_status'].startswith('pending'))
    timing=(f"El intervalo observado va de **{start.astimezone(local.tzinfo).strftime('%H:%M:%S')} a "
            f"{local.strftime('%H:%M:%S')} UTC−04:00**, aproximadamente **{progress['observed_wall_clock_minutes']:.2f} minutos de reloj**. "
            "Incluye investigación, curación, documentación y validación; no se midieron por separado horas efectivas. "
            "**No se alcanzaron ni se afirman las tres horas efectivas solicitadas.** Este lote acotado se entrega con sus pendientes para continuidad.")
    bibliography='| ID | Fuente | Idioma | Acceso registrado | Fecha del documento |\n|---|---|---|---|---|\n'
    for s in sources:
        bibliography+=f"| {s['id']} | [{s['title']}]({s['url']}) | {s['language']} | {s['access_level']} | {s['publication_date'] or 'No confirmada'} |\n"
    template=(HERE/'report_template.md').read_text(encoding='utf-8')
    for marker,value in {'COUNTS':summary,'TIMING':timing,'CATEGORIES':categories,'REMOVED_ALIASES':removed,
                         'ADVERSARIAL':adversarial,'PENDING':pending,'SOURCES':bibliography}.items():
        template=template.replace('{{'+marker+'}}',value)
    assert not re.search(r'\{\{[A-Z_]+\}\}',template)
    (HERE/'hypertension_research_report.md').write_text(template,encoding='utf-8')

    for path in HERE.glob('*.json'):
        json.loads(path.read_text(encoding='utf-8'))
    # Resolve all local Markdown links in the delivered narrative.
    for path in [HERE/'hypertension_research_report.md',HERE/'DATASET_SCHEMA.md']:
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' not in target and not re.match(r'^[A-Za-z]:',target):
                assert (HERE/target).is_file(), (path.name,target)
    deliverable_names=['hypertension_research_en_es.json','medical_base_en_extended_candidate.json',
                       'hypertension_research_report.md','hypertension_research_progress.json',
                       'DATASET_SCHEMA.md','sources.json','validation_results.json','original_glossary_audit.json',
                       'web_consultation_index.json','original_terms_review.txt','new_terms_review.txt',
                       'evidence_updates.json','build_research.py','finalize_research.py','report_template.md']
    manifest={'created_at':local.isoformat(timespec='seconds'),'original_unchanged':True,
              'files':[{'name':name,'bytes':(HERE/name).stat().st_size,
                        'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in deliverable_names]}
    write_json('manifest.json',manifest)
    archive=HERE/'hypertension_research_deliverables.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for name in [*deliverable_names,'manifest.json']:
            z.write(HERE/name,arcname=name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set([*deliverable_names,'manifest.json'])
        for f in manifest['files']:
            assert hashlib.sha256(z.read(f['name'])).hexdigest()==f['sha256']
    print(json.dumps({'status':'pass','counts':counts,'elapsed_wall_minutes':progress['observed_wall_clock_minutes'],
                      'original_unchanged':True,'archive':str(archive),'archive_bytes':archive.stat().st_size},ensure_ascii=True,indent=2))

if __name__=='__main__':
    main()

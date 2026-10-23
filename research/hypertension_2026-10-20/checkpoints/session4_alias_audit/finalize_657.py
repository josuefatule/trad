"""Validate and package the completed 657-pair research inventory.

The original glossary, operational candidate and production files are read-only.
Session timing excludes both idle gaps. This program applies reviewed decisions;
it never infers acceptance from unreviewed discovery matches.
"""
from collections import Counter
import copy,datetime as dt,hashlib,json,re,zipfile
from pathlib import Path
from verify_bilingual import norm
P=Path(__file__).resolve().parent; ROOT=P.parents[1]
BASE=P/'checkpoints/session2_600_verified'
ORIGINAL_SHA='4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896'
CANDIDATE_SHA='f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45'
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def base(n):return json.loads((BASE/n).read_text(encoding='utf-8'))
def save(n,x):(P/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if (P/'alias_review_decisions.json').exists():
  raise RuntimeError('Canonical checkpoint finalizer is historical after alias audit; use finalize_alias_audit.py to preserve that audit and its timing.')
 now=dt.datetime.now(dt.timezone.utc);stamp=now.isoformat(timespec='seconds')
 local=now.astimezone(dt.timezone(dt.timedelta(hours=-4)));localstamp=local.isoformat(timespec='seconds')
 original=ROOT/'glossaries/medical_base_en.json';candidate=P/'medical_base_en_extended_candidate.json'
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 old=base('bilingual_verification.json'); new=read('session3_verification.json')
 assert len(old['records'])==600 and len(new['records'])==57
 assert new['input_discovery_sha256']==sha(P/'session3_discovery.json')
 records=copy.deepcopy(old['records'])+copy.deepcopy(new['records'])
 approved={r['id']:r for r in records};assert len(approved)==657
 assert records[:600]==old['records']
 sources=read('sources.json');sm={s['id']:s for s in sources}
 corpus=read('source_cache/corpus.json');cm={s['source_id']:s for s in corpus}
 assert len(sm)==len(sources) and len(cm)==len(corpus)
 source_usage=Counter();attestation_count=0
 for r in records:
  assert r['independent_clinician_review']=='not_performed' and not r['automatic_substitution_approved']
  for lang in ['en','es']:
   a=r[lang+'_attestation'];s=cm[a['source_id']]; page=s['pages'][a['locator_index']-1]
   assert a['source_id'] in sm and a['url']==sm[a['source_id']]['url']==s['url']
   bilingual=s['locator_kind']=='indexed_bilingual_author_keywords' and lang in s['language'].split(',')
   assert s['language']==lang or bilingual
   assert a['locator_kind']==s['locator_kind']
   assert ' '+norm(a['form'])+' ' in ' '+norm(page)+' ',(r['canonical_en'],lang)
   assert a['extracted_locator_sha256']==hashlib.sha256(page.encode('utf-8')).hexdigest()
   assert a['source_copy_sha256']==s['sha256']
   assert 'checking your browser' not in page.casefold() and len(page)>20
   assert not (lang=='es' and a['source_id']=='S29' and a['locator_index']>=92),(r['canonical_en'],'English bibliography as Spanish')
   source_usage[a['source_id']]+=1;attestation_count+=1
  for extra in r.get('supplementary_context_sources',[]):
   assert extra['source_id'] in sm and extra['source_id'] in cm
   source=cm[extra['source_id']]
   assert extra['locator_kind']==source['locator_kind'] and 0<extra['locator_index']<=len(source['pages'])
 assert attestation_count==1314
 # Preserve accepted prior decisions and retain history for each resolved pending item.
 decision_file=base('bilingual_decisions.json');dm={d['id']:d for d in decision_file['decisions']}
 new_decisions=read('session3_review_decisions.json')['decisions']
 for d in new_decisions:
  previous=copy.deepcopy(dm[d['id']]);assert previous['decision']=='pending'
  revised=copy.deepcopy(d);revised['decision_history']=[previous]
  dm[d['id']]=revised
 ordered=[dm[d['id']] for d in decision_file['decisions']]
 assert len(ordered)==657 and all(d['decision']=='accepted_external_bilingual_crosscheck' for d in ordered)
 save('bilingual_decisions.json',dict(schema_version='1.1',reviewed_at_utc=stamp,policy='Assistant editorial decisions on two frozen discovery snapshots. Historical pending decisions remain in per-record history; new matches require a new review.',input_discovery_sha256_by_session={'session2':decision_file['input_discovery_sha256'],'session3':new['input_discovery_sha256']},counts=dict(reviewed_canonical_records=657,accepted=657,pending=0,historical_session2_discovery_pairs=609,session3_reviewed_pairs=57,session3_preferred_es_corrections=2),decisions=ordered))
 methods=Counter(r['method'] for r in records)
 ledger=copy.deepcopy(old)
 ledger.update(schema_version='1.1',updated_at_utc=stamp,counts=dict(verified=657,pending=0,previous_600_retained=600,newly_verified_session3=57),records=records,sessions=[dict(id='session2',verified_after=600),dict(id='session3',verified_after=657,newly_verified=57)],method_counts=dict(methods))
 ledger['locator_policy']='One-based PDF pages or local extraction blocks. Bilingual author-keyword lists are explicitly labeled and may attest both languages in a single record. Indexed text is not claimed as full-article reading.'
 save('bilingual_verification.json',ledger)
 # Update just the previously pending 57 concept records.
 data=base('hypertension_research_en_es.json');unchanged600={c['id']:copy.deepcopy(c) for c in data['concepts'] if c['id'] in {r['id'] for r in old['records']}}
 corrections=read('session3_terminology_corrections.json')['corrections'];correction_map={c['id']:c for c in corrections}
 new_ids={r['id'] for r in new['records']}
 for c in data['concepts']:
  if c['id'] not in new_ids:continue
  r=approved[c['id']];assert c['canonical_en']==r['canonical_en']
  if c['id'] in correction_map:
   fix=correction_map[c['id']];assert c['preferred_es']==fix['previous']
   c['preferred_es']=fix['corrected'];c.setdefault('terminology_revision_history',[]).append(fix)
   c['form_reviews'].append(dict(form=fix['previous'],language='es',status='replaced_research_preference_not_approved_as_automatic_alias',automatic_substitution_approved=False,reason=fix['reason']))
  assert c['preferred_es']==r['preferred_es']
  refs=[]
  for lang in ['en','es']:
   a=r[lang+'_attestation'];refs.append(a['source_id'])
   c['evidence'].append(dict(source_id=a['source_id'],locator=f"{a['locator_kind']} {a['locator_index']} (one-based)",supports='Individual canonical EN/preferred ES terminology crosscheck; no automatic aliases, dosing or clinical certification',language=lang,attested_form=a['form'],verification_record_id=c['id'],verification_session='session3'))
  c['source_ids']=list(dict.fromkeys(c['source_ids']+refs))
  c['notes'].append(r['editorial_note'])
  c['review'].update(concept_status='literature_supported_research_candidate',translation_status='crosschecked_in_en_and_es_sources',translation_crosscheck_source_ids=list(dict.fromkeys(refs)),translation_crosscheck_method=r['method'],translation_verification_record='bilingual_verification.json#'+c['id'],continuation_editorial_decision='accepted_external_bilingual_crosscheck',continuation_editorial_note=r['editorial_note'],verification_session='session3',independent_clinician_review='not_performed',operational_status='manual_review_required_not_approved')
 for c in data['concepts']:
  if c['id'] in unchanged600:assert c==unchanged600[c['id']]
 # Index actual access and source-copy integrity, distinguishing indexed metadata from full text.
 access=[]
 for s in sources:
  sid=s['id'];corp=cm.get(sid);kind=corp['locator_kind'] if corp else None
  size=sum(len(x) for x in corp['pages']) if corp else 0
  if kind and kind.startswith('indexed'):level=kind+'_read_not_full_article'
  elif not corp or size<500:level='not_accessible_in_current_corpus_or_challenge_only'
  elif kind=='pdf_page':level='full_pdf_available_selected_terminology_sections_checked'
  elif kind=='web_text_block_35_lines':level='web_extract_read_partial_document'
  else:level='downloaded_html_available_selected_terminology_checked'
  s.update(latest_access_level=level,bilingual_attestation_count=source_usage[sid])
  if int(sid[1:])>=131:s['access_level']=level
  files=[]
  paths=([P/'source_cache/esc2024_en.pdf'] if sid=='S71' else [])+sorted((P/'source_cache').glob(sid+'.*'))
  for f in paths:
   if f.suffix in ['.source','.txt'] or f.name=='esc2024_en.pdf':files.append(dict(filename=str(f.relative_to(P)).replace('\\','/'),bytes=f.stat().st_size,sha256=sha(f)))
  access.append(dict(source_id=sid,url=s['url'],latest_access_level=level,used_for_bilingual_verification=bool(source_usage[sid]),bilingual_attestation_count=source_usage[sid],locator_kind=kind,source_text_language=corp['language'] if corp else None,extracted_locator_count=len(corp['pages']) if corp else 0,extracted_text_sha256=hashlib.sha256(json.dumps(corp['pages'],ensure_ascii=False).encode('utf-8')).hexdigest() if corp else None,local_evidence_files=files))
 idx={x['source_id']:x for x in access}
 assert all(r[k]['source_copy_sha256'] in {f['sha256'] for f in idx[r[k]['source_id']]['local_evidence_files']} for r in records for k in ['en_attestation','es_attestation'])
 save('sources.json',sources)
 save('source_access_index.json',dict(updated_at_utc=stamp,policy='Available full source files were searched and relevant sections reviewed; availability does not mean every page was read. Indexed records, original titles and bilingual author keywords are explicitly labeled. Source copies excluded from ZIP.',sources=access))
 counts=data['counts'];counts.update(translations_crosschecked_in_external_en_es_sources=657,translations_pending_individual_source_check=0,literature_supported_research_candidates=657,pending_targeted_source_verification=0,consulted_sources=len(sources),sources_cited_by_individual_bilingual_crosschecks=len(source_usage),newly_verified_translations_this_session=57,previous_verified_translations_retained=600,preferred_es_corrections_this_session=2)
 data.update(schema_version='1.2.0',updated_at=localstamp,initial_research_date='2026-10-20',research_date=local.date().isoformat(),status='all_657_canonical_bilingual_pairs_crosschecked_research_only_not_integrated',counts=counts,sources=sources,counting_policy='657 stable canonical terminology records after the original grouping of 10 lexical variants; every canonical EN/preferred ES pair individually crosschecked in external sources. Includes clinical entities, drugs, procedures, units and conference/research vocabulary. Aliases/inflections do not add to the count and are not all verified; this is not 657 distinct diseases or independent clinician certification.',bilingual_verification=dict(file='bilingual_verification.json',decisions_file='bilingual_decisions.json',session3_file='session3_verification.json',corrections_file='session3_terminology_corrections.json',reviewer='assistant',verified=657,pending=0,independent_clinician_review='not_performed'))
 save('hypertension_research_en_es.json',data)
 progress=base('hypertension_research_progress.json');sessions=copy.deepcopy(progress['sessions'])
 start=dt.datetime.fromisoformat('2026-10-21T03:40:57+00:00')
 sessions.append(dict(id='session3',started_at_utc=start.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=round((now-start).total_seconds()/60,2),verified_before=600,verified_after=657))
 minutes=round(sum(x['observed_wall_clock_minutes'] for x in sessions),2)
 cats=Counter(c['category'] for c in data['concepts'])
 progress.update(updated_at=localstamp,checkpoint_at_utc=stamp,status='all_657_requested_bilingual_pairs_completed_no_integration',counts=counts,sessions=sessions,observed_wall_clock_minutes=minutes,effective_research_hours_measured=None,time_accounting='Sum of three observed session intervals, including research, curation and validation; both idle gaps are excluded. Active research hours were not separately measured; three effective hours are not claimed.',target=dict(verified_bilingual_concepts=657,achieved=True,verification_scope='Canonical EN/preferred ES individual external-source crosscheck by assistant, not independent clinician review'),category_counts=dict(cats),category_translation_counts={k:dict(total=n,verified=n,pending=0) for k,n in cats.items()},categories_fully_verified=list(cats),categories_pending=[],pending_concept_ids=[],pending_translation_ids=[],original_modified=False,original_sha256=ORIGINAL_SHA,final_original_sha256=ORIGINAL_SHA,candidate_modified_in_continuation=False,candidate_sha256=CANDIDATE_SHA,final_artifact_integrity_checks='pass',background_work=False,scheduled_automation=False,commits_created=False,integration_performed=False)
 progress['cycles_completed'] += [dict(cycle='B4',work='Targeted primary/official source checks for all final 57 pending records, maintaining priority domains and adding specialist Spanish texts.'),dict(cycle='C4',work='Resolved clinically important qualifier ambiguities, CARDIA/CARDia collision, English-only bibliography hits and two Spanish research preferences.'),dict(cycle='D5',work='Recorded 57 explicit editorial decisions with bilingual sources, attested forms, locators and hashes; preserved prior 600 records unchanged.'),dict(cycle='V4',work='Validated 657 decisions, 1,314 attestations, cross-file counts, source-copy hashes, unchanged protected files and ZIP integrity.')]
 progress['open_questions']=['Independent clinician/terminologist review remains unperformed.','Individual approval of all aliases, abbreviations and inflections remains outside the completed canonical-pair crosscheck.','No ASR, live translation or latency evaluation was performed; runtime integration requires a separate authorized task.','Terminology verification does not establish exhaustive current clinical recommendations, drug approvals, doses or diagnostic thresholds.']
 progress['next_research_line']='All 657 requested canonical bilingual pairs are crosschecked. No canonical translation IDs remain pending. Any future work should address independent specialist review or individual alias/context validation; do not modify the original glossary or integrate without a separate request.'
 progress['continuity_files']=['bilingual_verification.json','bilingual_decisions.json','session3_verification.json','session3_review_decisions.json','session3_terminology_corrections.json','source_access_index.json','sources.json','finalize_657.py','checkpoints/session2_600_verified','checkpoints/session1_52_verified']
 progress['sources_used']=[dict(id=s['id'],url=s['url'],access_level=s['access_level'],bilingual_attestation_count=source_usage[s['id']]) for s in sources if source_usage[s['id']]]
 save('hypertension_research_progress.json',progress)
 validation=base('validation_results.json');validation['counts']=counts
 validation['baseline_runtime_checks_repeated_in_session3']=False
 validation['baseline_runtime_checks_repeat_reason']='Only research evidence and documentation changed; original glossary and operational candidate remain byte-identical.'
 validation['limitations']=['All 657 canonical EN/preferred ES pairs were individually crosschecked; not every alias, abbreviation, inflection or possible clinical use was individually approved. Contextual renderings are explicitly distinguished from literal forms.','No independent clinician or terminologist certified the dataset.','No conference-audio benchmark, ASR benefit, latency or live translation-quality evaluation was performed.','Operational runtime checks are dated historical checks; the original glossary and candidate retain their bytes and baseline policies. These checks do not certify remaining baseline fuzzy substitutions.','Attestation of a medicine, procedure or historical guideline name does not verify current approval, indications, doses, formulations or exhaustive recommendation/corrigendum currency. Some term evidence is from explicitly labeled indexed extracts, original titles, abstracts or bilingual author keywords.']
 validation['bilingual_verification_checks']=dict(checked_at_utc=stamp,pass_=True,unique_canonical_records=657,approved_pairs=657,pending_pairs=0,individual_attestations_checked=attestation_count,prior_verified_retained=600,newly_verified=57,preferred_es_corrections=2,baseline_600_concept_and_verification_records_unchanged=True,method_counts=dict(methods),source_ids_urls_languages_and_locator_hashes_match=True,source_copy_hashes_match_local_files=True,no_challenge_pages_accepted=True,no_spanish_english_only_bibliography_hits_accepted=True,independent_clinician_review='not_performed')
 validation['final_artifact_integrity_checks']=dict(all_json_files_parse=True,cross_file_counts_match=True,source_reference_ids_exist=True,stable_concept_ids_unique=True,translations_count_consistent=True,no_new_automatic_corrections_enabled=True,original_hash_final=ORIGINAL_SHA,candidate_hash_final=CANDIDATE_SHA,candidate_unchanged_in_continuation=True,finalized_at=localstamp)
 validation['original_sha256_after']=sha(original);validation['original_unchanged']=True
 save('validation_results.json',validation)
 template=(P/'final_report_template.md').read_text(encoding='utf-8')
 rows='\n'.join(f"| {r['canonical_en']} | {r['preferred_es']} | {r['en_attestation']['source_id']} | {r['es_attestation']['source_id']} |" for r in new['records'])
 catrows='\n'.join(f'| {k} | {n} | {n} | 0 |' for k,n in cats.items())
 repl=dict(UPDATED=localstamp,SOURCES=str(len(sources)),CITED=str(len(source_usage)),SESSION3_MINUTES=str(sessions[-1]['observed_wall_clock_minutes']),MINUTES=f'{minutes:.2f}',LITERAL=str(methods['literal_pair']),CONTEXTUAL=str(methods['reviewed_terminological_variant_or_contextual_rendering']),NEW_PAIRS=rows,CATEGORIES=catrows)
 for k,v in repl.items():template=template.replace('{{'+k+'}}',v)
 assert not re.search(r'\{\{[A-Z_]+\}\}',template)
 (P/'hypertension_research_report.md').write_text(template,encoding='utf-8')
 (P/'CONTINUATION_README.txt').write_text((P/'final_readme_template.txt').read_text(encoding='utf-8'),encoding='utf-8')
 # Final independent cross-file checks before publication of a new manifest.
 assert len(data['concepts'])==len({c['id'] for c in data['concepts']})==657
 assert {c['id'] for c in data['concepts']}==approved.keys()
 assert all(c['review']['translation_status']=='crosschecked_in_en_and_es_sources' for c in data['concepts'])
 assert all(c['review']['concept_status']=='literature_supported_research_candidate' for c in data['concepts'])
 assert all(set(c['source_ids'])<=sm.keys() for c in data['concepts'])
 assert all(not c['ambiguity']['automatic_substitution_approved'] for c in data['concepts'])
 assert all(not c['grouped_lexical_forms_are_automatic_aliases'] for c in data['concepts'])
 assert data['counts']==read('validation_results.json')['counts']==read('hypertension_research_progress.json')['counts']
 for f in P.glob('*.json'):json.loads(f.read_text(encoding='utf-8'))
 for f in [P/'hypertension_research_report.md',P/'DATASET_SCHEMA.md']:
  for target in re.findall(r'\]\(([^)]+)\)',f.read_text(encoding='utf-8')):
   if '://' not in target and not target.startswith('#'):assert (P/target.split('#')[0]).exists(),(f,target)
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 names=['hypertension_research_en_es.json','hypertension_research_progress.json','hypertension_research_report.md','DATASET_SCHEMA.md','bilingual_verification.json','bilingual_decisions.json','session3_verification.json','session3_review_decisions.json','session3_terminology_corrections.json','sources.json','source_access_index.json','validation_results.json','medical_base_en_extended_candidate.json','original_glossary_audit.json','web_consultation_index.json','original_terms_review.txt','new_terms_review.txt','evidence_updates.json','bilingual_discovery.json','bilingual_search_forms.txt','session3_discovery.json','session3_search_forms.txt','verify_bilingual.py','prepare_corpus.py','discover_session3.py','record_session3_review.py','finalize_657.py','final_report_template.md','CONTINUATION_README.txt','fetch_source_cache.ps1','register_session3_sources.py']
 names.append('final_readme_template.txt')
 manifest=dict(created_at=localstamp,original_unchanged=True,candidate_unchanged_in_continuation=True,original_sha256=ORIGINAL_SHA,candidate_sha256=CANDIDATE_SHA,verified_bilingual_pairs=657,pending_bilingual_pairs=0,source_copies_excluded=True,previous_600_records_preserved=True,files=[dict(name=n,bytes=(P/n).stat().st_size,sha256=sha(P/n)) for n in names])
 save('manifest.json',manifest)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip','w',zipfile.ZIP_DEFLATED) as z:
  for n in names+['manifest.json']:z.write(P/n,n)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip') as z:
  assert z.testzip() is None and len(z.namelist())==len(names)+1
  for f in manifest['files']:assert hashlib.sha256(z.read(f['name'])).hexdigest()==f['sha256']
 print(json.dumps(dict(verified=657,pending=0,newly_verified=57,prior_600_preserved=True,preferred_es_corrections=2,attestations_validated=1314,cited_sources=len(source_usage),catalog_sources=len(sources),method_counts=dict(methods),original_unchanged=True,candidate_unchanged=True,archive_files=len(names)+1,checks='pass'),indent=2))
if __name__=='__main__':main()

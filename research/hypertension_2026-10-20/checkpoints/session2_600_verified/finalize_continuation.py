"""Apply reviewed evidence and package research-only deliverables.

Reads, hashes, and never writes the original glossary or operational candidate.
The fixed editorial ledger, not discovery string hits, controls verification.
"""
from collections import Counter
import datetime as dt
import hashlib, json, re, zipfile
from pathlib import Path
from verify_bilingual import norm
P=Path(__file__).resolve().parent
ROOT=P.parents[1]
BASE=P/'checkpoints/session1_52_verified'
ORIGINAL_SHA='4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896'
CANDIDATE_SHA='f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45'
def read(n): return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v): (P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 now=dt.datetime.now(dt.timezone.utc); stamp=now.isoformat(timespec='seconds')
 local=now.astimezone(dt.timezone(dt.timedelta(hours=-4))).isoformat(timespec='seconds')
 original=ROOT/'glossaries/medical_base_en.json'; candidate=P/'medical_base_en_extended_candidate.json'
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 data=json.loads((BASE/'hypertension_research_en_es.json').read_text(encoding='utf-8'))
 progress=json.loads((BASE/'hypertension_research_progress.json').read_text(encoding='utf-8'))
 validation=json.loads((BASE/'validation_results.json').read_text(encoding='utf-8'))
 sources=read('sources.json'); corpus=read('source_cache/corpus.json')
 cm={s['source_id']:s for s in corpus}; sm={s['id']:s for s in sources}
 assert len(cm)==len(corpus) and len(sm)==len(sources)
 ledger=read('bilingual_verification.json'); decisions=read('bilingual_decisions.json')
 verified={r['id']:r for r in ledger['records']}; reviewed={r['id']:r for r in decisions['decisions']}
 assert len(verified)==600 and len(reviewed)==657
 assert decisions['input_discovery_sha256']==sha(P/'bilingual_discovery.json')
 previous={c['id'] for c in data['concepts'] if c['review']['translation_status']=='crosschecked_in_en_and_es_sources'}
 assert len(previous)==52 and previous<=verified.keys()
 source_usage=Counter(); checks=0
 for c in data['concepts']:
  decision=reviewed[c['id']]
  assert decision['canonical_en']==c['canonical_en'] and decision['preferred_es']==c['preferred_es']
  c['review']['continuation_editorial_decision']=decision['decision']
  c['review']['continuation_editorial_note']=decision['reason']
  if c['id'] not in verified:
   assert decision['decision']=='pending'
   continue
  r=verified[c['id']]
  assert r['canonical_en']==c['canonical_en'] and r['preferred_es']==c['preferred_es']
  refs=[]
  for lang in ['en','es']:
   att=r[lang+'_attestation']; sid=att['source_id']; s=cm[sid]
   assert sid in sm and att['url']==sm[sid]['url']==s['url']
   assert s['language']==lang
   assert att['locator_kind']==s['locator_kind']
   page=s['pages'][att['locator_index']-1]
   assert ' '+norm(att['form'])+' ' in ' '+norm(page)+' '
   assert hashlib.sha256(page.encode('utf-8')).hexdigest()==att['extracted_locator_sha256']
   assert att['source_copy_sha256']==s['sha256']
   assert len(page)>20 and 'checking your browser' not in page.casefold()
   assert not (lang=='es' and sid=='S29' and att['locator_index']>=92), (c['canonical_en'],'Spanish hit is bibliography')
   refs.append(sid); source_usage[sid]+=1; checks+=1
   c['evidence'].append(dict(source_id=sid,locator=f"{att['locator_kind']} {att['locator_index']} (one-based)",supports='Individual canonical bilingual terminology crosscheck; no approval of every alias or treatment recommendation',language=lang,attested_form=att['form'],verification_record_id=c['id']))
  c['source_ids']=list(dict.fromkeys(c['source_ids']+refs))
  c['review'].update(concept_status='literature_supported_research_candidate',translation_status='crosschecked_in_en_and_es_sources',translation_crosscheck_source_ids=list(dict.fromkeys(refs)),translation_crosscheck_method=r['method'],translation_verification_record='bilingual_verification.json#'+c['id'],independent_clinician_review='not_performed',operational_status='manual_review_required_not_approved')
  if c['canonical_en']=='number needed to harm': c['notes'].append(r['editorial_note'])
 # Describe actual continuation access. A cached challenge or application shell is not a read article.
 access=[]
 for s in sources:
  sid=s['id']; c=cm.get(sid); size=sum(len(x) for x in c['pages']) if c else 0
  kind=c['locator_kind'] if c else None
  if sid in ['S125','S126','S127','S128']:
   level={'S125':'indexed_bilingual_author_keywords_read','S126':'indexed_spanish_abstract_read','S127':'indexed_spanish_original_title_read','S128':'indexed_spanish_original_title_read'}[sid]
  elif sid=='S105': level='indexed_spanish_abstract_read'
  elif not c or size<500: level='not_accessible_in_continuation_or_challenge_only'
  elif kind=='pdf_page': level='full_pdf_available_selected_terminology_sections_checked'
  elif kind and kind.startswith('indexed'): level='indexed_excerpt_read_not_full_article'
  elif kind=='web_text_block_35_lines': level='web_extract_read_partial_document'
  else: level='downloaded_html_available_selected_terminology_checked'
  s['continuation_access_level']=level
  if int(sid[1:])>=71: s['access_level']=level
  s['bilingual_attestation_count']=source_usage[sid]
  files=[]
  paths=([P/'source_cache/esc2024_en.pdf'] if sid=='S71' else [])+sorted((P/'source_cache').glob(sid+'.*'))
  for f in paths:
   if f.suffix in ['.source','.txt'] or f.name=='esc2024_en.pdf': files.append(dict(filename=str(f.relative_to(P)).replace('\\','/'),bytes=f.stat().st_size,sha256=sha(f)))
  access.append(dict(source_id=sid,url=s['url'],continuation_access_level=level,used_for_bilingual_verification=bool(source_usage[sid]),bilingual_attestation_count=source_usage[sid],locator_kind=kind,extracted_locator_count=len(c['pages']) if c else 0,extracted_text_sha256=hashlib.sha256(json.dumps(c['pages'],ensure_ascii=False).encode('utf-8')).hexdigest() if c else None,local_evidence_files=files))
 save('sources.json',sources)
 save('source_access_index.json',dict(updated_at_utc=stamp,policy='Source availability does not mean every page was read. Local source copies are excluded from the delivery archive.',sources=access))
 counts=data['counts']
 counts.update(translations_crosschecked_in_external_en_es_sources=600,translations_pending_individual_source_check=57,literature_supported_research_candidates=sum(c['review']['concept_status']=='literature_supported_research_candidate' for c in data['concepts']),pending_targeted_source_verification=sum(c['review']['concept_status'].startswith('pending') for c in data['concepts']),consulted_sources=len(sources),sources_cited_by_individual_bilingual_crosschecks=len(source_usage),newly_verified_translations_this_session=548,previous_verified_translations_retained=52)
 data.update(schema_version='1.1.0',updated_at=local,status='bilingual_target_600_reached_research_only_not_integrated',counts=counts,sources=sources,counting_policy='657 stable canonical terminology records after the baseline grouping of 10 lexical variants. 600 canonical EN↔preferred ES pairs individually crosschecked; 57 pending. Inventory includes clinical entities, drugs, methods, units and conference/research vocabulary. Aliases and inflections do not add to the verified count; this is not 600 distinct diseases or independent clinician certification.',bilingual_verification=dict(file='bilingual_verification.json',decisions_file='bilingual_decisions.json',reviewer='assistant',verified=600,pending=57,independent_clinician_review='not_performed'))
 save('hypertension_research_en_es.json',data)
 pending=[c for c in data['concepts'] if c['id'] not in verified]
 cats=Counter(c['category'] for c in data['concepts']); vcats=Counter(r['category'] for r in verified.values())
 start2=dt.datetime.fromisoformat('2026-10-20T22:18:30+00:00')
 sessions=[dict(id='session1',started_at_utc='2026-10-20T20:08:31+00:00',ended_at_utc='2026-10-20T20:36:06+00:00',observed_wall_clock_minutes=round(1655/60,2),verified_before=0,verified_after=52),dict(id='session2',started_at_utc=start2.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=round((now-start2).total_seconds()/60,2),verified_before=52,verified_after=600)]
 minutes=round(sum(s['observed_wall_clock_minutes'] for s in sessions),2)
 progress.update(updated_at=local,checkpoint_at_utc=stamp,status='requested_600_bilingual_target_reached_no_integration',counts=counts,sessions=sessions,observed_wall_clock_minutes=minutes,effective_research_hours_measured=None,time_accounting='Sum of observed session intervals, including curation and validation. The idle gap between 20:36:06 and 22:18:30 UTC is excluded. Active research hours were not separately measured; three effective hours are not claimed.',target=dict(verified_bilingual_concepts=600,achieved=True,verification_scope='Individual external EN/ES terminology crosscheck by assistant, without independent clinician review'),category_counts=dict(cats),category_translation_counts={k:dict(total=n,verified=vcats[k],pending=n-vcats[k]) for k,n in cats.items()},categories_fully_verified=[k for k,n in cats.items() if vcats[k]==n],categories_pending=[k for k,n in cats.items() if vcats[k]<n],pending_concept_ids=[c['id'] for c in data['concepts'] if c['review']['concept_status'].startswith('pending')],pending_translation_ids=[c['id'] for c in pending],original_modified=False,original_sha256=ORIGINAL_SHA,final_original_sha256=ORIGINAL_SHA,candidate_modified_in_continuation=False,candidate_sha256=CANDIDATE_SHA,final_artifact_integrity_checks='pass',background_work=False,scheduled_automation=False,commits_created=False,integration_performed=False)
 progress['cycles_completed'] += [dict(cycle='B3',work='Individual EN/ES attestation search across full guideline copies, official translations, primary publications and indexed abstracts.'),dict(cycle='C3',work='Editorial review of 609 discovered pairs; excluded 9 insufficient matches and replaced four Spanish bibliography hits with Spanish AHA medication lists.'),dict(cycle='D4',work='Retained 52 prior pairs and verified 548 pending translations; recorded paired sources, attested forms, locators, hashes and semantic notes.'),dict(cycle='V3',work='Cross-file counts, 1,200 attestations, source language/URL/locator checks, immutable glossary and candidate hashes, and archive integrity.')]
 progress['open_questions']=['Verify the remaining 57 preferred translations with individual EN/ES evidence, preserving clinical qualifiers.','Independent clinician/terminologist review remains unperformed.','Not every alias, abbreviation or morphological variant has been individually verified.','Current clinical recommendation/corrigendum completeness and any future ASR or runtime integration require their own review.']
 progress['next_research_line']='The requested 600-pair target is complete. For a future continuation, begin with pending_translation_ids and bilingual_decisions.json; do not rebuild from the historical 52-pair builder or modify the original glossary/candidate.'
 progress['continuity_files']=['bilingual_verification.json','bilingual_decisions.json','source_access_index.json','sources.json','hypertension_research_progress.json','finalize_continuation.py','checkpoints/session1_52_verified']
 used=set(source_usage)
 progress['sources_used']=[dict(id=s['id'],url=s['url'],access_level=s['access_level'],bilingual_attestation_count=source_usage[s['id']]) for s in sources if s['id'] in used]
 save('hypertension_research_progress.json',progress)
 validation['counts']=counts
 validation['baseline_runtime_checks_performed_at']='2026-10-20T16:36:06-04:00'
 validation['baseline_runtime_checks_repeated_in_continuation']=False
 validation['baseline_runtime_checks_repeat_reason']='Only research evidence and documentation changed; the original glossary and operational candidate are byte-identical.'
 validation['bilingual_verification_checks']=dict(checked_at_utc=stamp,pass_=True,unique_canonical_records=657,approved_pairs=600,pending_pairs=57,individual_attestations_checked=checks,prior_verified_retained=52,newly_verified=548,discovery_pairs=609,excluded_discovery_pairs=9,spanish_bibliography_matches_relocated_to_spanish_body=4,literal_normalized_pairs=385,reviewed_variants_or_contextual_renderings=215,source_ids_urls_languages_and_locator_hashes_match=True,no_challenge_pages_accepted=True,independent_clinician_review='not_performed')
 validation['final_artifact_integrity_checks']=dict(all_json_files_parse=True,cross_file_counts_match=True,source_reference_ids_exist=True,stable_concept_ids_unique=True,translations_count_consistent=True,no_new_automatic_corrections_enabled=True,original_hash_final=ORIGINAL_SHA,candidate_hash_final=CANDIDATE_SHA,candidate_unchanged_in_continuation=True,finalized_at=local)
 validation['original_sha256_after']=sha(original); validation['original_unchanged']=True
 save('validation_results.json',validation)
 category_rows='\n'.join(f'| {k} | {n} | {vcats[k]} | {n-vcats[k]} |' for k,n in cats.items())
 pending_rows='\n'.join(f"| {c['id']} | {c['canonical_en']} | {c['preferred_es']} |" for c in pending)
 exclusion_rows='\n'.join(f"- **{d['canonical_en']}**: {d['reason']}" for d in decisions['decisions'] if d['canonical_en'] in __import__('record_bilingual_review').EXCLUDED)
 template=(P/'continuation_report_template.md').read_text(encoding='utf-8')
 replacements={'UPDATED':local,'CONCEPT_SUPPORTED':str(counts['literature_supported_research_candidates']),'CONCEPT_PENDING':str(counts['pending_targeted_source_verification']),'SOURCES':str(len(sources)),'CITED':str(len(source_usage)),'MINUTES':f'{minutes:.2f}','SESSION2_MINUTES':str(sessions[1]['observed_wall_clock_minutes']),'CATEGORIES':category_rows,'PENDING':pending_rows,'EXCLUSIONS':exclusion_rows}
 for key,value in replacements.items(): template=template.replace('{{'+key+'}}',value)
 assert not re.search(r'\{\{[A-Z_]+\}\}',template)
 (P/'hypertension_research_report.md').write_text(template,encoding='utf-8')
 # Integrity across all deliverables, including links and the ledger.
 for f in P.glob('*.json'): json.loads(f.read_text(encoding='utf-8'))
 for f in [P/'hypertension_research_report.md',P/'DATASET_SCHEMA.md']:
  for target in re.findall(r'\]\(([^)]+)\)',f.read_text(encoding='utf-8')):
   if '://' not in target and not target.startswith('#'): assert (P/target.split('#')[0]).exists(),(f,target)
 assert len({c['id'] for c in data['concepts']})==657
 assert all(set(c['source_ids'])<=sm.keys() for c in data['concepts'])
 assert all(not c['ambiguity']['automatic_substitution_approved'] for c in data['concepts'])
 assert sum(c['review']['translation_status']=='crosschecked_in_en_and_es_sources' for c in data['concepts'])==600
 assert data['counts']==read('validation_results.json')['counts']==read('hypertension_research_progress.json')['counts']
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 names=['hypertension_research_en_es.json','hypertension_research_progress.json','hypertension_research_report.md','DATASET_SCHEMA.md','bilingual_verification.json','bilingual_decisions.json','sources.json','source_access_index.json','validation_results.json','medical_base_en_extended_candidate.json','original_glossary_audit.json','web_consultation_index.json','original_terms_review.txt','new_terms_review.txt','evidence_updates.json','bilingual_discovery.json','bilingual_search_forms.txt','verify_bilingual.py','prepare_corpus.py','record_bilingual_review.py','finalize_continuation.py','continuation_report_template.md','CONTINUATION_README.txt','fetch_source_cache.ps1','add_continuation_sources.py','register_last_sources.py']
 manifest=dict(created_at=local,original_unchanged=True,candidate_unchanged_in_continuation=True,original_sha256=ORIGINAL_SHA,candidate_sha256=CANDIDATE_SHA,verified_bilingual_pairs=600,pending_bilingual_pairs=57,source_copies_excluded=True,files=[dict(name=n,bytes=(P/n).stat().st_size,sha256=sha(P/n)) for n in names])
 save('manifest.json',manifest)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip','w',zipfile.ZIP_DEFLATED) as z:
  for n in names+['manifest.json']: z.write(P/n,n)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip') as z:
  assert z.testzip() is None
  assert len(z.namelist())==len(names)+1
  for f in manifest['files']: assert hashlib.sha256(z.read(f['name'])).hexdigest()==f['sha256']
 print(json.dumps(dict(verified=600,pending=57,newly_verified=548,concept_supported=counts['literature_supported_research_candidates'],concept_pending=counts['pending_targeted_source_verification'],attestations_validated=checks,cited_sources=len(source_usage),original_unchanged=True,candidate_unchanged=True,archive_files=len(names)+1,checks='pass'),indent=2))
if __name__=='__main__': main()

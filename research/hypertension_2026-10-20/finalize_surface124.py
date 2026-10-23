"""Validate and deliver the targeted 124-surface continuation, research only."""
import json,hashlib,datetime as dt,re,zipfile,copy
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from verify_bilingual import norm
P=Path(__file__).resolve().parent;ROOT=P.parents[1];BASE=P/'checkpoints/session4_alias_audit'
ORIGINAL_SHA='4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896'
CANDIDATE_SHA='f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45'
LABELS={'literal_verified_in_concept_context':'Atestación aceptada en contexto','unsafe_equivalence_reconfirmed':'Equivalencia estricta rechazada','ambiguous_reference_restricted':'Referente ambiguo: restringir','limited_evidence_not_accepted':'Evidencia limitada: no aceptada','no_acceptable_literal_attestation':'Sin atestación literal aceptable'}
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def oldread(n):return json.loads((BASE/n).read_text(encoding='utf-8'))
def main():
 now=dt.datetime.now(dt.timezone.utc);stamp=now.isoformat(timespec='seconds');local=now.astimezone(dt.timezone(dt.timedelta(hours=-4))).isoformat(timespec='seconds')
 original=ROOT/'glossaries/medical_base_en.json';candidate=P/'medical_base_en_extended_candidate.json'
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 frozen=['hypertension_research_en_es.json','bilingual_verification.json','bilingual_decisions.json','sources.json','source_access_index.json','session3_verification.json','session3_review_decisions.json','session3_terminology_corrections.json','alias_review_decisions.json','alias_inventory.json','alias_corrections_proposed.json','alias_definition_evidence.json','alias_source_catalog.json']
 for n in frozen:assert sha(P/n)==sha(BASE/n),('Changed protected research input',n)
 targets=read('surface_verification_124_targets.json');ledger=read('surface_verification_124.json');catalog=read('surface_verification_124_sources.json');records=ledger['records'];sources={s['id']:s for s in catalog['sources']};old=oldread('alias_review_decisions.json');oldforms={r['form_id']:r for r in old['form_reviews']};tm={r['form_id']:r for r in targets['targets']}
 assert len(records)==len({r['form_id'] for r in records})==124
 assert tm.keys()=={r['form_id'] for r in old['form_reviews'] if not r['literal_location']}=={r['form_id'] for r in records}
 assert targets['baseline_alias_review_sha256']==ledger['baseline_alias_review_sha256']==sha(P/'alias_review_decisions.json')
 assert ledger['input_targets_sha256']==sha(P/'surface_verification_124_targets.json')
 assert ledger['input_discovery_sha256']==sha(P/'surface_verification_124_discovery.json')
 assert Counter(r['decision'] for r in records)==ledger['counts']['by_decision']
 assert sum(ledger['counts']['by_decision'].values())==124
 assert ledger['counts']['accepted_literal_in_concept_context']==106 and ledger['counts']['literal_verification_still_not_accepted']==13
 literal_checks=0
 for r in records:
  prior=oldforms[r['form_id']]
  for field in ['concept_id','canonical_en','language','form','occurrence_ids']:assert r[field]==prior[field]
  assert r['previous_alias_safety_status']==prior['status'] and not r['automatic_substitution_approved']
  a=r['attestation']
  if a:
   s=sources[a['source_id']];f=P/a['local_cache_file'];assert sha(f)==a['cache_sha256']
   b=f.read_text(encoding='utf-8').split('--------------------------------------------------------------------------------')[a['result_block_index']-1].strip()
   assert hashlib.sha256(b.encode('utf-8')).hexdigest()==a['result_block_sha256']
   assert a['url']==s['url'] and a['url'] in b.splitlines()[0]
   assert ' '+norm(r['form'])+' ' in ' '+norm(b)+' '
   if a['language_basis']=='explicit_spanish_original_title_in_pubmed':assert 'Original title:' in b
   if a['language_basis']=='explicit_spanish_title_and_bilingual_author_keywords_in_pubmed':assert 'Keywords:' in b and 'Preterm birth' in b and 'nacimiento pretérmino' in b.casefold()
   if a['language_basis']=='explicit_spanish_other_abstract_in_pubmed_index':assert '## Other abstract' in b
   if a['language_basis']=='explicit_spanish_resumen_on_publisher_page':assert 'Resumen' in b and 'clevidipina' in b.casefold()
   if r['form_id']=='UF0424':assert 'Renovascular' in b and 'Prueba de captopril' in b
   if r['form_id']=='UF0557':assert 'Acute Coronary Syndromes' in b
   literal_checks+=1
 assert literal_checks==114
 assert all(not s['full_article_read_claimed'] for s in sources.values())
 # A deliverable search index contains provenance, not long copied source extracts.
 discovery=read('surface_verification_124_discovery.json')
 slim=[]
 for r in discovery['records']:
  slim.append(dict(form_id=r['form_id'],form=r['form'],language=r['language'],candidate_count=len(r['candidates']),candidates=[{k:v for k,v in c.items() if k not in {'normalized_context_before','normalized_context_after'}} for c in r['candidates']]))
 save('surface_verification_124_search_index.json',dict(policy='Discovery only; rejected/irrelevant results may appear and are not evidence of acceptance. Long source excerpts are excluded from delivery. Source snapshots remain local.',input_discovery_sha256=sha(P/'surface_verification_124_discovery.json'),records=slim))
 unresolved=[r for r in records if r['decision'] in {'no_acceptable_literal_attestation','limited_evidence_not_accepted'}]
 semantic=[r for r in records if r['decision'] in {'unsafe_equivalence_reconfirmed','ambiguous_reference_restricted'} or r['form_id']=='UF0015']
 corrections=dict(policy='Research-only continuation overlay; no lists are written back into the original glossary, candidate, canonical dataset or previous alias audit.',input_alias_audit_sha256=sha(P/'alias_review_decisions.json'),semantic_restrictions=[dict(form_id=r['form_id'],concept_id=r['concept_id'],form=r['form'],language=r['language'],previous_safety_status=r['previous_alias_safety_status'],decision=r['decision'],research_action=r['research_action'],reason=r['editorial_note'],attestation_source_id=r['attestation']['source_id'] if r['attestation'] else None) for r in semantic],forms_without_accepted_literal_attestation=[dict(form_id=r['form_id'],concept_id=r['concept_id'],canonical_en=r['canonical_en'],preferred_es=r['preferred_es'],form=r['form'],language=r['language'],reason=r['editorial_note'],action=r['research_action']) for r in unresolved],all_previous_context_restrictions_preserved=True,automatic_substitution_approved=False)
 save('surface_verification_124_corrections.json',corrections)
 # Record the actual query batches. The first eleven are reconstructed from the
 # explicit tool calls; the remaining records were saved with their calls.
 early={
 '01':['"hipertensión farmacológica" (site:who.int OR site:pubmed.ncbi.nlm.nih.gov OR site:heart.org OR site:escardio.org)','"variabilidad tensional" (site:pubmed.ncbi.nlm.nih.gov OR site:heart.org OR site:escardio.org)','"presión arterial en consulta" (site:heart.org OR site:who.int)','"automedición domiciliaria de la presión arterial" (site:who.int OR site:pubmed.ncbi.nlm.nih.gov OR site:heart.org)'],
 '02':['"presión arterial fuera de consulta" (site:heart.org OR site:who.int OR site:pubmed.ncbi.nlm.nih.gov)','"stage two hypertension" (site:heart.org OR site:acc.org OR site:who.int)','"2017 ACC/AHA hypertension guideline" site:acc.org','"guideline-directed management" site:acc.org hypertension'],
 '03':['"manejo orientado por guías" hipertensión','"meta de tratamiento" hipertensión (site:who.int OR site:heart.org)','"coordinador conjunto" (site:who.int OR site:escardio.org OR site:heart.org)','"carga salina" aldosteronismo (site:pubmed.ncbi.nlm.nih.gov OR site:who.int)'],
 '04':['"hyponatraemia"','"hypernatraemia"','"hypokalaemic metabolic alkalosis"','"nonpharmacologic therapy" hypertension'],
 '05':['"non-pharmacologic therapy" hypertension','"alpha-adrenergic blockers"','"hormonal replacement therapy"','"tratamiento hormonal sustitutivo"'],
 '06':['"immunosuppressants" hypertension','"haemorrhagic stroke"','"AFib" "atrial fibrillation" site:heart.org','"healthy dietary pattern" site:heart.org'],
 '07':['"restricción dietética de sodio"','"potassium-supplemented salt"','"sugary drinks" site:heart.org','"bebidas endulzadas con azúcar"'],
 '08':['"aerobic training" hypertension','"ejercicio dinámico de resistencia"','"ejercicio de resistencia isométrica"','"moderation of alcohol consumption" hypertension'],
 '09':['"dietary counselling" hypertension','"millimetres of mercury"','"µg/day" aldosterone','"mcg/day" hypertension'],
 '10':['"µg/día" aldosterona','"mcg/dL" aldosterone','"µg/dL" aldosterona','"plasma levels" aldosterone'],
 '11':['"brazalete de presión arterial"','"tensiómetro oscilométrico"','"diferencia interbraquial de presión arterial"','"relación presión-natriuresis"']}
 queries=[]
 for n,qs in early.items():
  f=P/f'source_cache/surface124_search{n}.web.txt';assert f.exists()
  queries.append(dict(batch=n,queries=qs,domains=['escardio.org','acc.org','heart.org','pubmed.ncbi.nlm.nih.gov','who.int','kdigo.org'] if int(n)>=4 else None,metadata_provenance='Reconstructed from the actual explicit tool arguments in this session.',snapshot_file=str(f.relative_to(P)).replace('\\','/'),snapshot_sha256=sha(f)))
 for f in sorted((P/'source_cache').glob('surface124_search*.queries.json')):
  n=re.search(r'search(\d+)',f.name).group(1);assert n not in early
  q=json.loads(f.read_text(encoding='utf-8'));snap=P/f'source_cache/surface124_search{n}.web.txt'
  queries.append(dict(batch=n,**q,metadata_provenance='Saved with the actual tool call.',snapshot_file=str(snap.relative_to(P)).replace('\\','/'),snapshot_sha256=sha(snap)))
 assert len(queries)==57 and sum(len(q['queries']) for q in queries)==228
 save('surface_verification_124_search_log.json',dict(policy='Priority-domain searches first, then complementary Spanish primary/institutional sources and exact-form followups. A query with no useful results is not evidence that the phrase does not exist anywhere.',batch_count=57,query_count=228,batches=queries))
 # Report: literal support is deliberately separate from synonym safety.
 countrows='\n'.join('| '+LABELS[k]+' | '+str(n)+' |' for k,n in ledger['counts']['by_decision'].items())
 lines=['# Verificación dirigida de las 124 formas alternativas','',f'Cierre: {local}, hora de Bolivia. **Solo investigación; sin cambios en TRAD.**','',
 '**Se revisaron individualmente las 124 formas que no tenían coincidencia literal en el corpus anterior.** Se aceptaron atestaciones en el contexto del concepto para 106; se reconfirmaron 3 exclusiones de equivalencia estricta y se restringieron 2 referencias ambiguas. Otras 13 formas siguen sin atestación aceptada: 10 sin una fuente literal adecuada y 3 con evidencia limitada. Ninguna se aprobó para sustitución automática.','',
 '| Decisión | Formas |','|---|---:|',countrows,'| Total revisado | **124** |','',
 'Los 106 casos aceptados no pasan a ser sinónimos incondicionales. Se mantienen las restricciones de contexto, idioma, gramática, temporalidad, muestra y magnitud de la auditoría anterior. Una atestación de sigla, unidad, nombre de fármaco o guía no valida dosis, indicaciones, vigencia de recomendaciones ni rendimiento del reconocimiento de voz. Los 657 pares canónicos bilingües y el estado de la auditoría previa se preservan íntegros.','',
 '## Fuentes y alcance de la verificación','',
 f"Se registraron 228 consultas en 57 lotes. Se seleccionaron {ledger['counts']['sources_selected']} URL de fuentes; {ledger['counts']['priority_domain_sources']} pertenecen a los dominios prioritarios o sus subdominios. Se priorizaron ESC, ACC, AHA, PubMed, OMS y KDIGO, y se recurrió a fuentes españolas institucionales o de editoriales científicas cuando faltaba la formulación. Las URL seleccionadas pueden coincidir con referencias ya consultadas: no se cuentan como 113 publicaciones nuevas ni como 113 ensayos primarios.",'',
 'El nivel de acceso consta por fuente y por forma: pasaje web directo seleccionado, extracto indexado, resumen, título original español, palabras clave bilingües o bloque Other abstract. Hospedar un documento nacional en la web de la OMS no lo convierte en una guía redactada por la OMS. La disponibilidad de una copia completa tampoco equivale a lectura exhaustiva. Las coincidencias de búsqueda y los resultados descartados se conservan separados de las decisiones.','',
 '## Correcciones y restricciones destacadas','']
 for r in semantic:
  a=r['attestation'];cite=f" [{a['source_id']}]({a['url']})" if a else ' Fuente contextual: registro canónico previo; no se encontró atestación literal aceptable de la variante.'
  lines.append(f"- **{r['form']} → {r['canonical_en']}**: {r['editorial_note']}{cite}")
 lines+=['','Las tres exclusiones reconfirmadas —coordinador conjunto, relación presión-natriuresis y carga de medicación— ya estaban restringidas en la auditoría anterior. La ambigüedad de prueba de captopril precisa ahora otra finalidad diagnóstica concreta. El alias hipertensión farmacológica se propone retirar por falta de respaldo literal aceptable y ambigüedad frente a hipertensión inducida por fármacos. El año y las sociedades sin el tema hipertensión tampoco identifican inequívocamente una guía.','',
 '## Controles que evitaron falsos positivos','',
 '- KCL dentro de un correo institucional no se aceptó como cloruro de potasio. Se utilizó una definición química de la OMS para KCl.',
 '- Cor Vitae no se aceptó como clase de recomendación; COR se cotejó con un suplemento de ACC.',
 '- Las coincidencias portuguesas de plaquetopenia y atrofia encefálica no se presentaron como evidencia de español.',
 '- Tirotropina alfa como producto recombinante no se usó para atestar por sí sola el analito TSH. Se seleccionó una definición de MedlinePlus.',
 '- La unidad µg/dL se marcó como símbolo independiente del idioma cuando la fuente era inglesa; no se presentó ese pasaje como prosa española.',
 '- Se conservaron prefijos, denominadores, números de tipo, non-fatal, agudo, embarazo/posparto, vigilia/sueño y la diferencia entre UACR y UPCR.','',
 'El manual de Paraguay de 2013 se descargó para comprobar la prueba de captopril. El visor web rechazó el documento por tamaño y la copia local de 58 páginas no produjo texto extraíble. **No se inventó una página PDF:** la relación con la causa renovascular se apoya en la fila explícita de la tabla 13 recuperada por el índice. La copia descargada y su huella quedan registradas, pero no se usan como atestación textual adicional.','',
 '## Las 13 formas que no se aprueban como literalmente verificadas','',
 '| Forma | Concepto | Motivo y acción |','|---|---|---|']
 for r in unresolved:lines.append(f"| {r['form']} ({r['language']}) | {r['canonical_en']} | {r['editorial_note']} |")
 lines+=['','No encontrar una atestación en esta búsqueda no demuestra que la expresión nunca se use. Estas 13 decisiones son explícitas y revisables; no se sustituyen por coincidencias parciales, traducciones inferidas o fuentes de otro idioma para aparentar que están verificadas. Para su eventual adopción literal hace falta una fuente específica aceptable.','',
 '## Registro individual de las 124 decisiones','',
 '| ID | Forma | Concepto | Decisión | Fuente |','|---|---|---|---|']
 for r in records:
  a=r['attestation'];cite=f"[{a['source_id']}]({a['url']})" if a else 'Contexto canónico previo; sin fuente literal aceptada'
  if r['decision']=='limited_evidence_not_accepted':cite+=' (evidencia limitada)'
  if r['decision'] in {'unsafe_equivalence_reconfirmed','ambiguous_reference_restricted'}:cite+=' (no confirma equivalencia estricta)'
  lines.append(f"| {r['form_id']} | {r['form']} ({r['language']}) | {r['canonical_en']} | {LABELS[r['decision']]} | {cite} |")
 lines+=['','## Archivos y continuidad','',
 '- [Decisiones y atestaciones de las 124 formas](surface_verification_124.json).',
 '- [Correcciones y restricciones propuestas](surface_verification_124_corrections.json).',
 '- [Fuentes seleccionadas y sus niveles de acceso](surface_verification_124_sources.json).',
 '- [Registro de consultas](surface_verification_124_search_log.json) e [índice de descubrimiento sin aprobación automática](surface_verification_124_search_index.json).',
 '- [Validación](surface_verification_124_validation.json), [progreso actualizado](hypertension_research_progress.json) y [paquete completo](hypertension_research_deliverables.zip).','',
 'Los archivos de descubrimiento con fragmentos amplios y las copias de fuentes quedan únicamente en el caché local y fuera del ZIP. Repetir las verificaciones textuales exige conservar o recuperar las fuentes identificadas. El estado anterior íntegro está en checkpoints/session4_alias_audit/.','',
 'El glosario original, el candidato operacional, el dataset canónico y los registros bilingües permanecen byte por byte intactos. La auditoría anterior también conserva sus listas y decisiones. Esta continuación añade una capa de investigación y actualiza documentación, progreso y paquete. No hubo integración en TRAD, cambio de configuración, commit, automatización ni certificación clínica independiente.','']
 (P/'surface_verification_124_report.md').write_text('\n'.join(lines),encoding='utf-8')
 # Preserve past session timing and add only this observed interval.
 prior=oldread('hypertension_research_progress.json');progress=copy.deepcopy(prior);start=dt.datetime.fromisoformat(targets['started_at_utc']);minutes=round((now-start).total_seconds()/60,2)
 progress.update(updated_at=local,checkpoint_at_utc=stamp,status='124_missing_surface_forms_reviewed_research_only_no_integration',surface_verification_124=dict(started_at_utc=start.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=minutes,counts=ledger['counts'],report='surface_verification_124_report.md',ledger='surface_verification_124.json',corrections='surface_verification_124_corrections.json',canonical_pairs_unchanged=657,original_and_candidate_unchanged=True,integration_performed=False),sessions=copy.deepcopy(prior['sessions'])+[dict(id='session5_surface_forms',started_at_utc=start.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=minutes,forms_reviewed=124,accepted_literal_in_concept_context=106,unaccepted_literal_attestations=13,canonical_verified_before=657,canonical_verified_after=657)],observed_wall_clock_minutes=round(prior['observed_wall_clock_minutes']+minutes,2),time_accounting='Sum of five observed session intervals; all idle gaps excluded. Active research hours were not measured separately. Session5 concerns alternative forms, not 124 new canonical concepts.',counts_scope='Canonical counts and previous broad alias-audit counts are historical snapshots retained unchanged. Targeted continuation counts are in surface_verification_124.counts; neither 443 earlier search hits nor 106 targeted accepted forms certify all alternatives as strict synonyms.')
 progress['open_questions']=['13 targeted alternative forms lack an accepted literal attestation (10 no adequate exact source, 3 limited-source findings); all have explicit research decisions.','Five located forms retain exclusion or reference restrictions; hypertension farmacológica is additionally proposed for withdrawal.','Independent clinical/terminologist certification remains unperformed.','No ASR, dose/formulation interchangeability, live translation or runtime benefit evaluation was performed.']
 progress['next_research_line']='The 124 requested forms have individual research decisions. Remaining literal adoption requires adequate evidence for the 13 unaccepted forms; do not modify the original glossary or integrate in TRAD.'
 progress['continuity_files']=list(dict.fromkeys(progress['continuity_files']+['surface_verification_124_report.md','surface_verification_124.json','surface_verification_124_corrections.json','surface_verification_124_sources.json','surface_verification_124_search_log.json','surface_verification_124_validation.json','finalize_surface124.py','checkpoints/session4_alias_audit']))
 save('hypertension_research_progress.json',progress)
 validation=dict(checked_at_utc=stamp,pass_=True,targets_covered_exactly_once=124,accepted_literal_in_context=106,reconfirmed_unsafe_equivalences=3,ambiguous_references_restricted=2,unaccepted_literal_forms=13,no_adequate_literal_source=10,limited_evidence_cases=3,literal_locations_validated=114,source_references_and_hashes_checked=True,original_title_and_other_abstract_language_labels_checked=True,no_automatic_substitution_enabled=True,previous_research_files_preserved={n:sha(P/n) for n in frozen},original_sha256=sha(original),candidate_sha256=sha(candidate),original_unchanged=True,candidate_unchanged=True,canonical_dataset_unchanged=True,canonical_verification_ledger_unchanged=True,previous_alias_audit_unchanged=True,query_batches=57,queries=228,runtime_tests_run=False,integration_performed=False,independent_clinician_review='not_performed')
 save('surface_verification_124_validation.json',validation)
 overall=oldread('validation_results.json');overall['latest_surface_form_verification']=dict(file='surface_verification_124_validation.json',counts=ledger['counts'],pass_=True);save('validation_results.json',overall)
 old_report=(BASE/'hypertension_research_report.md').read_text(encoding='utf-8')
 (P/'hypertension_research_report.md').write_text('> **Continuación posterior:** [verificación individual de las 124 formas](surface_verification_124_report.md). 106 atestaciones aceptadas en contexto; 3 exclusiones reconfirmadas; 2 referentes restringidos; 13 formas sin atestación aceptada. El texto siguiente conserva los cierres anteriores.\n\n'+old_report,encoding='utf-8')
 (P/'alias_audit_report.md').write_text('> **Actualización posterior:** [verificación de las 124 formas sin coincidencia literal previa](surface_verification_124_report.md). La auditoría que sigue es la instantánea anterior; no describe el estado posterior de atestación de esas 124 formas.\n\n'+(BASE/'alias_audit_report.md').read_text(encoding='utf-8'),encoding='utf-8')
 schema=(BASE/'DATASET_SCHEMA.md').read_text(encoding='utf-8')+'\n\n## Continuación de las 124 formas sin coincidencia previa\n\nsurface_verification_124_targets.json congela los 124 form_id del estado anterior. surface_verification_124.json añade exactamente una decisión por forma, conservando concepto, idioma, grafía, procedencia y estado previo de seguridad. La cifra de 106 indica atestación aceptada en contexto, no sinonimia incondicional. Otras 3 formas mantienen exclusión, 2 necesitan precisar referente, 3 tienen evidencia limitada y 10 carecen de una fuente literal aceptable. No hay decisiones editoriales pendientes; 13 atestaciones siguen sin aceptarse.\n\nLos localizadores tool_result_block_one_based identifican un bloque del resultado almacenado; no son páginas PDF ni números de línea del artículo. cache_sha256 protege la copia y result_block_sha256 el bloque recortado con strip. language_basis identifica títulos originales españoles, palabras clave bilingües, Other abstract español, resumen del editor o símbolo independiente del idioma. No se usa prosa inglesa como fuente española salvo un símbolo de unidad explícitamente independiente de lengua. SF identifica el catálogo complementario; no renumera S ni AS.\n\nsurface_verification_124_corrections.json es una capa de propuestas sin aplicación. surface_verification_124_sources.json conserva nivel de acceso y no afirma lectura completa. El índice de búsqueda no aprueba resultados, incluso si contiene Wikipedia, publicidad, otro idioma o un homónimo descartado. Los fragmentos extensos de descubrimiento y las copias de fuentes no se incluyen en el ZIP. Los estados históricos se mantienen y la capa actual se consulta junto a ellos. finalize_alias_audit.py queda protegido para no sobrescribir esta continuación; usar finalize_surface124.py solo para validar y empaquetar trabajo real, sin simular tiempo.\n'
 (P/'DATASET_SCHEMA.md').write_text(schema,encoding='utf-8')
 readme='CONTINUACIÓN DE 124 FORMAS REVISADA, SOLO INVESTIGACIÓN.\nLeer surface_verification_124_report.md y surface_verification_124.json.\n106 atestaciones aceptadas en contexto, 3 exclusiones reconfirmadas,\n2 referentes restringidos, 13 atestaciones no aceptadas (10 + 3 limitadas).\nNo se habilitan sustituciones automáticas. Los 657 pares canónicos,\nel original, el candidato y la auditoría previa conservan sus bytes.\nEl estado anterior está en checkpoints/session4_alias_audit/.\nUsar finalize_surface124.py para validar esta continuación.\nLas secciones siguientes describen cierres históricos.\n\n'+(BASE/'CONTINUATION_README.txt').read_text(encoding='utf-8')
 (P/'CONTINUATION_README.txt').write_text(readme,encoding='utf-8')
 for n in frozen:assert sha(P/n)==sha(BASE/n)
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 for f in P.glob('*.json'):json.loads(f.read_text(encoding='utf-8'))
 for n in ['surface_verification_124_report.md','hypertension_research_report.md','alias_audit_report.md','DATASET_SCHEMA.md']:
  for target in re.findall(r'\]\(([^)]+)\)',(P/n).read_text(encoding='utf-8')):
   if '://' not in target and not target.startswith('#'):assert (P/target.split('#')[0]).exists(),(n,target)
 prior_manifest=oldread('manifest.json');names=[f['name'] for f in prior_manifest['files']]+['surface_verification_124_targets.json','surface_verification_124.json','surface_verification_124_sources.json','surface_verification_124_corrections.json','surface_verification_124_search_log.json','surface_verification_124_search_index.json','surface_verification_124_report.md','surface_verification_124_validation.json','discover_surface124.py','prepare_surface124_review.py','record_surface124_review.py','finalize_surface124.py']
 assert len(names)==len(set(names))
 manifest=dict(created_at=local,original_unchanged=True,candidate_unchanged_in_continuation=True,canonical_dataset_and_bilingual_ledger_unchanged_in_alias_audit=True,previous_alias_review_ledger_unchanged=True,original_sha256=ORIGINAL_SHA,candidate_sha256=CANDIDATE_SHA,verified_bilingual_pairs=657,pending_bilingual_pairs=0,alias_audit_concepts=657,alias_forms_reviewed=567,alias_occurrences=900,surface_verification_124=ledger['counts'],source_copies_and_long_search_excerpts_excluded=True,files=[dict(name=n,bytes=(P/n).stat().st_size,sha256=sha(P/n)) for n in names])
 save('manifest.json',manifest)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip','w',zipfile.ZIP_DEFLATED) as z:
  for n in names+['manifest.json']:z.write(P/n,n)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip') as z:
  assert z.testzip() is None and len(z.namelist())==len(names)+1
  for f in manifest['files']:assert hashlib.sha256(z.read(f['name'])).hexdigest()==f['sha256']
 print(json.dumps(dict(checks='pass',counts=ledger['counts'],protected_research_files=len(frozen),original_unchanged=True,candidate_unchanged=True,canonical_ledger_unchanged=True,prior_alias_ledger_unchanged=True,archive_files=len(names)+1),ensure_ascii=False,indent=2))
if __name__=='__main__':main()

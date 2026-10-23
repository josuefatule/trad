"""Validate and package the alias safety overlay; canonical/operational files are read-only."""
import datetime as dt,hashlib,json,re,zipfile,copy
from collections import Counter,defaultdict
from pathlib import Path
from prepare_alias_audit import sha,tokens
from verify_bilingual import norm
P=Path(__file__).resolve().parent;ROOT=P.parents[1];BASE=P/'checkpoints/session3_657_verified'
ORIGINAL_SHA='4a4920d3ff9404db5601c1c8f832dde4fdeb180dc95d3f06037576ec726c2896'
CANDIDATE_SHA='f70199e00efd516220f33c6c36f500ed220992b2caa6bba0d85cdf9b2086ae45'
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def source_link(sid,sm):return f"[{sid}]({sm[sid]['url']})"
def main():
 now=dt.datetime.now(dt.timezone.utc);stamp=now.isoformat(timespec='seconds');local=now.astimezone(dt.timezone(dt.timedelta(hours=-4))).isoformat(timespec='seconds')
 original=ROOT/'glossaries/medical_base_en.json';candidate=P/'medical_base_en_extended_candidate.json'
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 frozen=['hypertension_research_en_es.json','bilingual_verification.json','bilingual_decisions.json','sources.json','source_access_index.json','session3_verification.json','session3_review_decisions.json','session3_terminology_corrections.json']
 for name in frozen:assert sha(P/name)==sha(BASE/name),('Protected canonical research changed',name)
 d=read('hypertension_research_en_es.json');audit=read('alias_review_decisions.json');inv=read('alias_inventory.json');counts=audit['counts']
 cm={c['id']:c for c in d['concepts']};sources=read('sources.json');extra=read('alias_source_catalog.json')['sources'];sm={s['id']:s for s in sources+extra}
 corpus={s['source_id']:s for s in read('source_cache/corpus.json')}
 assert len(cm)==len(audit['concept_coverage'])==657 and len(audit['form_reviews'])==567 and len(inv['occurrences'])==900
 assert audit['input_inventory_sha256']==sha(P/'alias_inventory.json') and audit['input_dataset_sha256']==sha(P/'hypertension_research_en_es.json')
 assert {r['concept_id'] for r in audit['concept_coverage']}==cm.keys()
 assert all(r['review_status']=='completed_editorial_safety_audit' for r in audit['concept_coverage'])
 occurrence_ids=[oid for r in audit['form_reviews'] for oid in r['occurrence_ids']]
 assert len(occurrence_ids)==len(set(occurrence_ids))==900
 assert set(occurrence_ids)=={r['occurrence_id'] for r in inv['occurrences']}
 assert len({(r['concept_id'],r['language'],r['form']) for r in audit['form_reviews']})==567
 assert Counter(r['status'] for r in audit['form_reviews'])==counts['by_status']
 assert sum(r['unique_alternative_form_count'] for r in audit['concept_coverage'])==567
 assert sum(r['alternative_occurrence_count'] for r in audit['concept_coverage'])==900
 assert all(not r['automatic_substitution_approved'] for r in audit['form_reviews'])
 assert counts['internal_collision_groups']==3 and {c['normalized_form'] for c in audit['internal_collisions']}=={'mra','eca','pad'}
 assert len(audit['near_form_decisions'])==counts['near_form_pairs_reviewed']==60
 for r in audit['form_reviews']:
  a=r['literal_location']
  if a:
   s=corpus[a['source_id']];text=s['pages'][a['locator_index']-1]
   assert ' '+norm(r['form'])+' ' in ' '+norm(text)+' '
   assert a['source_copy_sha256']==s['sha256'] and a['url']==s['url']
   assert a['extracted_locator_sha256']==hashlib.sha256(text.encode('utf-8')).hexdigest()
 for r in extra:
  f=P/r['local_snapshot'];assert sha(f)==r['snapshot_sha256']
  blocks=f.read_text(encoding='utf-8').split('--------------------------------------------------------------------------------')
  assert any(r['url'] in b and r['attested_short_expression'].casefold() in b.casefold() and hashlib.sha256(b.encode('utf-8')).hexdigest()==r['result_block_sha256'] for b in blocks)
 # Explicit glossary/definition locations reviewed, distinct from 443 search hits.
 pins=[
  ('S29',8,'PAD','presión arterial diastólica'),('S29',8,'ECA','enzima convertidora de angiotensina'),('S29',8,'PA','presión arterial'),('S29',8,'HRV','hipertensión renovascular'),('S29',8,'RAR','ratio aldosterona-renina'),('S29',8,'AMPA','automedida de la presión arterial'),('S29',8,'SAOS','síndrome de apnea obstructiva del sueño'),('S29',8,'IAH','índice de apnea-hipopnea'),
  ('S89',8,'ECA','ensayo controlado aleatorizado'),('S10',6,'PA','primary aldosteronism'),('S10',7,'PRA','plasma renin activity'),('S10',8,'ACS','autonomous cortisol secretion'),
  ('S71',6,'MRA','mineralocorticoid receptor antagonist'),('S71',6,'CI','confidence interval'),('S71',6,'ARR','aldosterone-to-renin ratio'),('S71',6,'ARB','angiotensin receptor blocker'),('S71',6,'CCB','calcium channel blocker'),
  ('S41',7,'HR','heart rate'),('S05',6,'HR','hazard ratio'),('S17',9,'MR','mineralocorticoid receptor'),('S188',6,'MR','magnetic resonance'),('S98',8,'IC','insuficiencia cardiaca'),('S98',8,'PEG','pequeño para la edad gestacional'),('S64',6,'IC','intervalo de confianza')]
 proofs=[]
 for sid,i,short,expansion in pins:
  s=corpus[sid];text=s['pages'][i-1];n=' '+norm(text)+' '
  assert ' '+norm(short)+' ' in n and ' '+norm(expansion)+' ' in n,(sid,i,short,expansion)
  proofs.append(dict(evidence_id=f'AD{len(proofs)+1:03}',source_id=sid,url=s['url'],locator_kind=s['locator_kind'],locator_index=i,form=short,expansion=expansion,source_copy_sha256=s['sha256'],extracted_locator_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),assessment='Explicit glossary/definition passage reviewed; expansion remains context dependent.'))
 for s in extra:
  proofs.append(dict(evidence_id=f'AD{len(proofs)+1:03}',source_id=s['id'],url=s['url'],access_level=s['access_level'],locator=s['locator'],form_or_subject=s['attested_short_expression'],snapshot_sha256=s['snapshot_sha256'],result_block_sha256=s['result_block_sha256'],assessment='Specifically checked selected passage; stated access level applies, not full-paper review.'))
 for group in audit['external_homographs']:
  assert set(group['source_ids'])<=sm.keys()
  group['definition_evidence_ids']=[p['evidence_id'] for p in proofs if p['source_id'] in group['source_ids'] and (p.get('form')==group['form'] or p['source_id'].startswith('AS'))]
  assert group['definition_evidence_ids']
 for g in audit['internal_collisions']:
  ids={'pad':['S29','AS02'],'eca':['S29','S89'],'mra':['S71','AS01']}[g['normalized_form']]
  g.update(source_ids=ids,decision='block_unconditional_expansion',correction='Require a local explicit definition and language; keep full concept names distinct.',definition_evidence_ids=[p['evidence_id'] for p in proofs if p['source_id'] in ids and (p.get('form','').casefold()==g['normalized_form'] or p['source_id'].startswith('AS'))])
 save('alias_definition_evidence.json',dict(policy='Specific definition/identity evidence used by the safety audit. One-based PDF pages or explicitly named local extraction blocks. This is not a new set of verified canonical concepts.',records=proofs))
 audit['definition_evidence_file']='alias_definition_evidence.json';save('alias_review_decisions.json',audit)
 # Separate correction overlay preserves the raw lists and the original attribution.
 excluded=[r for r in audit['form_reviews'] if r['status']=='exclude_strict_equivalence'];conditional=[r for r in audit['form_reviews'] if r['status']=='contextual_equivalence']
 proposal=dict(policy='Research overlay, not a runtime glossary. Apply no automatic substitutions. Raw research inventory, original glossary and operational candidate remain byte-identical.',input_dataset_sha256=sha(P/'hypertension_research_en_es.json'),exclude_from_strict_alias_sets=[dict(form_id=r['form_id'],concept_id=r['concept_id'],canonical_en=r['canonical_en'],language=r['language'],form=r['form'],occurrence_ids=r['occurrence_ids'],proposed_action=r['editorial_reason']) for r in excluded],retain_only_with_conditions=[dict(form_id=r['form_id'],concept_id=r['concept_id'],form=r['form'],language=r['language'],condition=r['editorial_reason']) for r in conditional],abbreviation_expansion_proposals=audit['expansion_correction_proposals'],abbreviation_other_meanings_proposals=audit['other_meanings_metadata_corrections'],block_unconditional_expansion_of=[c['normalized_form'] for c in audit['internal_collisions']],external_homograph_forms=[g['form'] for g in audit['external_homographs']],automatic_substitution_approved=False)
 save('alias_corrections_proposed.json',proposal)
 # Readable complete audit, with direct source links beside the claims.
 lines=['# Auditoría de alias, siglas y variantes de los 657 conceptos','',f'Cierre: {local}, hora de Bolivia. **Solo investigación; ninguna integración en TRAD.**','',
 '**Se revisaron los 657 conceptos, las 900 apariciones de alternativas y las 567 formas distintas por concepto e idioma.** Se identificaron 3 colisiones internas, 16 ambigüedades con acepciones externas, 11 equivalencias que deben excluirse como alias estrictos y 47 equivalencias condicionadas. Se proponen 6 ajustes de expansión y 22 de metadatos. El cribado completo de semejanza dentro de cada idioma produjo 60 pares que deben mantenerse separados.','',
 'El registro editorial de los 657 conceptos está completo. Esto no convierte las alternativas en 567 sinónimos verificados externamente: 443 tienen una coincidencia literal normalizada de búsqueda y 124 no la tienen en el corpus consultado. Ninguna coincidencia prueba por sí sola el significado ni la lengua del pasaje; puede aparecer en referencias, ejemplos u otro contexto. Las definiciones comprobadas específicamente están separadas en alias_definition_evidence.json. No se aprueba ninguna sustitución automática.','',
 '## Alcance y recuento','',
 '| Elemento | Cantidad |','|---|---:|',f"| Conceptos con alternativas / sin alternativas | {counts['concepts_with_alternatives']} / {counts['concepts_without_alternatives']} |",'| Alias EN / variantes ES / objetos de sigla | 306 / 243 / 176 |','| Alias heredados / variantes heredadas / formas agrupadas adicionales | 145 / 20 / 10 |','| Total de apariciones, sin descartar procedencia repetida | 900 |','| Formas únicas por concepto, idioma y grafía | 567 |','| Cadenas canónicas EN y ES incluidas como destinos de colisión | 1.314 |','| Conceptos canónicos bilingües preservados / pendientes | 657 / 0 |',
 '', 'Las 900 apariciones se solapan entre campos. Por ejemplo, una sigla puede figurar como alias, abreviatura y alias heredado. Los recuentos de hallazgos tampoco se suman como errores independientes: una forma puede requerir contexto y además una corrección de metadatos. Las 10 formas agrupadas ya tenían prohibida la conversión automática en alias.','',
 '## Colisiones internas comprobadas','',
 '| Forma | Conceptos diferentes | Corrección propuesta | Evidencia |','|---|---|---|---|',
 f"| PAD | Presión arterial diastólica (ES); peripheral artery disease (EN) | Exigir idioma y definición local; conservar ambos nombres completos | {source_link('S29',sm)}, PDF 8; {source_link('AS02',sm)} |",
 f"| ECA | Ensayo controlado aleatorizado; enzima convertidora de angiotensina (ambos ES) | El idioma no resuelve la colisión; conservar la expansión definida en el pasaje | {source_link('S89',sm)}, bloque 8; {source_link('S29',sm)}, PDF 8 |",
 f"| MRA | Mineralocorticoid receptor antagonist; magnetic resonance angiography (ambos EN) | Distinguir fármaco/clase de técnica de imagen; conservar singular/plural en la frase | {source_link('S71',sm)}, PDF 6; {source_link('AS01',sm)} |",'',
 'Son colisiones en el inventario de investigación ampliado, no tres fallos nuevos demostrados en el glosario operacional. El recuento histórico de una colisión en el lote inicial tenía otro alcance y queda conservado como antecedente. No se ejecutó el normalizador ni se midieron sustituciones en audio.','',
 '## Ambigüedades con acepciones externas','',
 'Estas 16 advertencias no añaden conceptos ni colisiones exactas al inventario. La acepción competidora puede no estar incluida como alias en él. Las fuentes y localizadores verificables están en el registro de definiciones.','',
 '| Forma | Acepción del inventario | Acepción competidora | Decisión y fuentes |','|---|---|---|---|']
 for g in audit['external_homographs']:lines.append(f"| {g['form']} | {g['inventory_meaning']} | {g['competing_meaning']} | {g['correction']} "+', '.join(source_link(s,sm) for s in g['source_ids'])+' |')
 lines+=['',f"Se comprobó RAR con {source_link('AS16',sm)}: la fuente andina S93 emplea **RRA**, por lo que esa fuente no se presenta como atestación de la grafía RAR. La guía española usa RAR para aldosterona/renina. Las advertencias históricas adicionales (p. ej., NO, MAP y significados secundarios no comprobados de MRAs/APA/AF) se conservan separadas; no se promocionan a acepciones verificadas en esta sesión.",'',
 '## Equivalencias que deben retirarse de los alias estrictos','',
 'Se documentan las 11 relaciones rechazadas. Se conserva cada cadena original para trazabilidad; su retirada se propone únicamente en la capa de investigación. El fundamento aquí es la diferencia de entidad, alcance o categoría gramatical, no una prueba de rendimiento del sistema.','',
 '| Concepto | Forma | Corrección propuesta |','|---|---|---|']
 for r in excluded:lines.append(f"| {r['canonical_en']} | {r['form']} ({r['language']}) | {r['editorial_reason']} |")
 lines+=['','## Expansiones y metadatos','',
 '| Sigla | Expansión anterior | Propuesta de investigación |','|---|---|---|']
 for f in audit['expansion_correction_proposals']:lines.append(f"| {f['form']} | {f['previous']} | {f['proposed']} |")
 lines += ['',f"AMPA y SAOS se cotejaron con el glosario de {source_link('S29',sm)}, PDF 8. Las otras cuatro propuestas preservan el número gramatical; las guías también pueden usar la sigla sin s para designar una clase en plural. Por eso no se impone una expansión singular en toda oración. Las formas plurales MRAs, ARBs, CCBs y NSAIDs se conservan separadas.",'',
 'En 22 objetos de abreviatura se propone limpiar other_meanings: retirar la propia expansión del campo de significados alternativos y separar las notas vagas o los plurales deducidos sin evidencia específica. Retener una advertencia histórica no certifica todas sus acepciones. El detalle anterior/propuesto y el motivo de cada retirada están en alias_corrections_proposed.json.','',
 '## Equivalencias que solo deben conservarse con condiciones','',
 '| Concepto | Forma | Condición de uso |','|---|---|---|']
 for r in conditional:lines.append(f"| {r['canonical_en']} | {r['form']} ({r['language']}) | {r['editorial_reason']} |")
 lines+=['',f"El uso amplio de thiazide-type está explícito en {source_link('AS04',sm)}, PDF 25; se contrasta con la distinción thiazide/thiazide-like de {source_link('S71',sm)}, PDF 47–48. Se usa la fuente de 2012 para documentar variación terminológica histórica. No se adopta ninguna recomendación terapéutica antigua.",'',f"Para vigilia/sueño, {source_link('S76',sm)}, bloque 12, distingue los periodos y pide un diario; {source_link('S71',sm)}, PDF 22, también requiere registrar el sueño. El uso contextual de clinical inertia se encuentra en {source_link('AS14',sm)}. Estas referencias apoyan la decisión de conservar contexto, no una sustitución universal.",'',
 '## Grafías parecidas y calificadores protegidos','',
 'Se compararon todas las formas y destinos canónicos de un mismo idioma con longitud normalizada de al menos 8 caracteres, usando SequenceMatcher ≥0,90. El filtro por longitud solo descarta parejas cuyo máximo matemático no alcanza el umbral. Se conservaron dígitos, letras de subtipo y negaciones. Los 60 resultados se revisaron como conceptos distintos; no son puntuaciones del motor operacional ni una prueba de todos los errores posibles de ASR.','',
 '| Idioma | Forma A | Forma B | Similitud de caracteres |','|---|---|---|---:|']
 for r in audit['near_form_decisions']:lines.append(f"| {r['language']} | {r['form_a']} | {r['form_b']} | {r['character_ratio']:.3f} |")
 lines+=['','Además se registran 51 barreras de distinción clínica, incluidas relaciones de subtipo o solapamiento que no constituyen sinonimia. Se mantienen, entre otras, hipopotasemia/hiperpotasemia, hipoxemia/hipoxia, TFG medida/estimada, actividad/concentración de renina, primera orina matutina/muestra aislada, FGR/SGA, emergencia/urgencia y HR/RR/OR. Las unidades conservan prefijo y denominador; no se convierten mg, µg, ng, mmol ni cantidades por día en cantidades por decilitro.','',
 f"Se protegen 47 etiquetas de referencia completas. CARDIA (cohorte) y CARDia (ensayo de revascularización) son referencias distintas: {source_link('S156',sm)}, {source_link('AS03',sm)}. STEP y STEP-1 también aparecen separados en el glosario de {source_link('S71',sm)}, PDF 6. Se mantienen los sufijos OFF/ON MED, TRIO, BPLA y los años de las guías. No se deduce una rama concreta de ACCORD o ASCOT a partir del nombre abreviado.",'',
 '## Archivos y límites','',
 '- [Decisiones completas de 567 formas y cobertura de 657 conceptos](alias_review_decisions.json).',
 '- [Correcciones propuestas, sin aplicación operacional](alias_corrections_proposed.json).',
 '- [Inventario de 900 apariciones con rutas de procedencia](alias_inventory.json).',
 '- [Definiciones específicamente comprobadas](alias_definition_evidence.json) y [20 referencias complementarias con nivel de acceso](alias_source_catalog.json).',
 '- [Descubrimiento literal y similitud, separado de las decisiones](alias_evidence_discovery.json).',
 '- [Validación de integridad de esta auditoría](alias_audit_validation.json), [progreso](hypertension_research_progress.json) y [paquete completo](hypertension_research_deliverables.zip).','',
 'La revisión es editorial del asistente. No hubo certificación clínica independiente, evaluación de audio, ensayo de traducción en vivo ni autorización de corrección automática. Las 124 formas sin coincidencia literal siguen identificadas como no atestadas individualmente en el corpus; antes de aprobarlas como alias estrictos requieren fuente específica. La revisión de seguridad está cerrada porque para todas las formas hay una decisión, incluso si consiste en conservar contexto o retener la aprobación.','',
 'El glosario original, el candidato operacional, el dataset canónico de investigación y los 657 registros de verificación se preservan byte por byte. Las correcciones viven en archivos nuevos de investigación. El estado previo íntegro está en checkpoints/session3_657_verified/. No hubo integración, cambio de configuración, commit ni automatización.','']
 (P/'alias_audit_report.md').write_text('\n'.join(lines),encoding='utf-8')
 # Preserve the prior session's counts and time as a named historical snapshot.
 progress=read('hypertension_research_progress.json');historical=json.loads((BASE/'hypertension_research_progress.json').read_text(encoding='utf-8'))
 start=dt.datetime.fromisoformat('2026-10-21T04:42:34+00:00');elapsed=round((now-start).total_seconds()/60,2)
 progress.update(updated_at=local,checkpoint_at_utc=stamp,status='alias_safety_audit_completed_for_657_concepts_research_only_no_integration',alias_audit=dict(started_at_utc=start.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=elapsed,counts=counts,report='alias_audit_report.md',decisions='alias_review_decisions.json',corrections='alias_corrections_proposed.json',validation='alias_audit_validation.json',canonical_dataset_unchanged=True,original_and_candidate_unchanged=True,integration_performed=False),counts_scope='Canonical verification/session3 historical counts retained unchanged. Current alias-audit counts are in alias_audit.counts; its three internal collision groups supersede the narrower original scan.',sessions=copy.deepcopy(historical['sessions'])+[dict(id='session4_alias_audit',started_at_utc=start.isoformat(),ended_at_utc=stamp,observed_wall_clock_minutes=elapsed,canonical_verified_before=657,canonical_verified_after=657,alternative_forms_reviewed=567)],observed_wall_clock_minutes=round(historical['observed_wall_clock_minutes']+elapsed,2),time_accounting='Sum of four observed session intervals; idle gaps excluded. Active research hours were not measured separately. Session4 is an alias safety audit, not 657 new canonical verifications.')
 progress['open_questions']=['Independent clinical/terminologist certification remains unperformed.','124 alternative surface forms have no literal location in the searched corpus; all have an editorial safety decision and no automatic substitution approval.','No ASR, live translation, dose/formulation interchangeability or runtime benefit evaluation was performed.','Historical secondary acronym meanings outside the specifically checked definition register remain warnings, not verified expansions.']
 progress['next_research_line']='Requested alias safety review completed. Any future strict-alias approval should resolve the 124 unattested surfaces and obtain specialist review; original glossary and TRAD remain unchanged.'
 progress['continuity_files']=list(dict.fromkeys(progress['continuity_files']+['alias_audit_report.md','alias_review_decisions.json','alias_corrections_proposed.json','alias_definition_evidence.json','alias_source_catalog.json','finalize_alias_audit.py','checkpoints/session3_657_verified']))
 save('hypertension_research_progress.json',progress)
 validation=dict(checked_at_utc=stamp,pass_=True,concept_coverage=657,unique_forms_reviewed=567,occurrences_covered_exactly_once=900,internal_collision_groups=3,near_pairs_reviewed=60,external_homograph_groups=16,specific_definition_evidence_records=len(proofs),new_supplementary_source_records=len(extra),lexical_hit_hashes_checked=443,missing_literal_forms_explicit=124,unconditional_automatic_substitutions=0,canonical_and_source_files_preserved={n:sha(P/n) for n in frozen},original_sha256=sha(original),candidate_sha256=sha(candidate),original_unchanged=True,candidate_unchanged=True,canonical_dataset_byte_identical=True,bilingual_ledger_byte_identical=True,runtime_tests_run=False,normalizer_read_only_sha256=sha(ROOT/'app/captions/terminology_normalizer.py'),normalizer_comparison_scope='Analytical token folding only; actual runtime span/join/precedence behavior was not executed. No production writes.',independent_clinician_review='not_performed')
 save('alias_audit_validation.json',validation)
 oldvalidation=read('validation_results.json');oldvalidation['latest_alias_audit']=dict(file='alias_audit_validation.json',counts=counts,pass_=True,original_and_candidate_unchanged=True,canonical_ledger_unchanged=True);save('validation_results.json',oldvalidation)
 # Add an explicit current pointer without rewriting the previous canonical report.
 report=(BASE/'hypertension_research_report.md').read_text(encoding='utf-8')
 (P/'hypertension_research_report.md').write_text('> **Auditoría posterior de alias completada:** [informe de alias, siglas y variantes](alias_audit_report.md). Cubre los 657 conceptos y propone correcciones únicamente en investigación. El texto siguiente conserva el cierre de la verificación canónica anterior.\n\n'+report,encoding='utf-8')
 schema=(BASE/'DATASET_SCHEMA.md').read_text(encoding='utf-8')
 schema+='\n\n## Auditoría posterior de alias (solo investigación)\n\nEl dataset canónico conserva sus bytes. alias_inventory.json enumera 900 ocurrencias y 1.314 destinos canónicos EN/ES. occurrence_id identifica campo y procedencia; form_id agrupa por concepto, idioma y grafía exacta. alias_review_decisions.json contiene 567 decisiones y concept_coverage incluye los 657 conceptos, incluidos 301 sin alternativas. El listado crudo se consulta junto a esta capa de revisión, no se considera un conjunto de alias aprobados.\n\nLos estados distinguen exclusión de equivalencia estricta, equivalencia contextual, sigla con definición obligatoria, colisión, grafía, flexión, unidad y variante de consulta. automatic_substitution_approved es siempre false. literal_location solo señala una coincidencia normalizada: no demuestra significado, sinonimia o idioma del pasaje. Las 124 formas sin coincidencia permanecen explícitas; no se eliminan ni se declaran verificadas externamente.\n\nalias_corrections_proposed.json contiene propuestas sin aplicación: 11 exclusiones, 47 condiciones, 6 expansiones y 22 ajustes de metadatos. Las 3 colisiones internas, 16 advertencias externas y 60 pares similares tienen distinto alcance y no se suman como errores independientes. alias_definition_evidence.json separa 24 localizadores de definiciones del corpus previo y 20 referencias complementarias de alias_source_catalog.json; los niveles indexados/resumen no prueban lectura de artículos completos. Los IDs AS no sustituyen ni renumeran S01–S191.\n\nLos recuentos counts del dataset/progreso anterior son una instantánea de la fase canónica. Los actuales están en alias_audit.counts y alias_audit_validation.json. La auditoría añade un cuarto intervalo observado y preserva todos los anteriores. finalize_657.py queda protegido contra reescribir esta fase; finalize_alias_audit.py valida y empaqueta la capa de revisión sin escribir el original, el candidato ni el dataset canónico. No reejecutar finalizadores para simular tiempo transcurrido de investigación.\n'
 (P/'DATASET_SCHEMA.md').write_text(schema,encoding='utf-8')
 readme=(BASE/'CONTINUATION_README.txt').read_text(encoding='utf-8')
 (P/'CONTINUATION_README.txt').write_text('AUDITORÍA POSTERIOR DE ALIAS COMPLETADA, SOLO INVESTIGACIÓN.\nLeer primero alias_audit_report.md y alias_corrections_proposed.json.\n657 conceptos / 900 ocurrencias / 567 formas únicas revisadas.\n3 colisiones internas; 16 advertencias externas; 11 exclusiones estrictas;\n47 condiciones; 6 expansiones; 22 metadatos; 60 pares similares separados.\n124 formas sin coincidencia literal individual siguen explícitas.\nOriginal, candidato, dataset canónico y registro bilingüe intactos.\nNo integración. Usar finalize_alias_audit.py para validar esta capa;\nfinalize_657.py se conserva como finalizador histórico protegido.\nLos párrafos siguientes describen el cierre canónico anterior.\n\n'+readme.replace('finalize_657.py valida y empaqueta el estado actual.','finalize_657.py validaba y empaquetaba el estado canónico anterior.'),encoding='utf-8')
 for f in P.glob('*.json'):json.loads(f.read_text(encoding='utf-8'))
 # Package exactly the previous delivery plus the research overlay and its tools.
 prior=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
 names=[f['name'] for f in prior['files']]+['alias_inventory.json','alias_inventory_review.txt','alias_evidence_discovery.json','alias_review_decisions.json','alias_corrections_proposed.json','alias_definition_evidence.json','alias_source_catalog.json','alias_audit_report.md','alias_audit_validation.json','prepare_alias_audit.py','screen_alias_evidence.py','review_aliases.py','register_alias_sources.py','finalize_alias_audit.py']
 assert len(names)==len(set(names))
 for n in ['alias_audit_report.md','hypertension_research_report.md','DATASET_SCHEMA.md']:
  for target in re.findall(r'\]\(([^)]+)\)',(P/n).read_text(encoding='utf-8')):
   if '://' not in target and not target.startswith('#'):assert (P/target.split('#')[0]).exists(),(n,target)
 for n in frozen:assert sha(P/n)==sha(BASE/n)
 assert sha(original)==ORIGINAL_SHA and sha(candidate)==CANDIDATE_SHA
 manifest=dict(created_at=local,original_unchanged=True,candidate_unchanged_in_continuation=True,canonical_dataset_and_bilingual_ledger_unchanged_in_alias_audit=True,original_sha256=ORIGINAL_SHA,candidate_sha256=CANDIDATE_SHA,verified_bilingual_pairs=657,pending_bilingual_pairs=0,alias_audit_concepts=657,alias_forms_reviewed=567,alias_occurrences=900,source_copies_excluded=True,previous_600_records_preserved=True,files=[dict(name=n,bytes=(P/n).stat().st_size,sha256=sha(P/n)) for n in names])
 save('manifest.json',manifest)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip','w',zipfile.ZIP_DEFLATED) as z:
  for n in names+['manifest.json']:z.write(P/n,n)
 with zipfile.ZipFile(P/'hypertension_research_deliverables.zip') as z:
  assert z.testzip() is None and len(z.namelist())==len(names)+1
  for f in manifest['files']:assert hashlib.sha256(z.read(f['name'])).hexdigest()==f['sha256']
 print(json.dumps(dict(checks='pass',counts=counts,definition_evidence_records=len(proofs),original_unchanged=True,candidate_unchanged=True,canonical_dataset_unchanged=True,bilingual_ledger_unchanged=True,archive_files=len(names)+1),ensure_ascii=False,indent=2))
if __name__=='__main__':main()

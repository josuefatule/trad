"""Materialize the assistant's review of the final 57 fixed-snapshot pairs.

No search hit is approved without this explicit review. Only research artifacts
are written. The prior 600 verification records are preserved byte-for-byte as
JSON values; no operational glossary or candidate is written.
"""
import copy,datetime as dt,hashlib,json
from pathlib import Path
from verify_bilingual import norm,find
P=Path(__file__).resolve().parent
BASE=P/'checkpoints/session2_600_verified'
SNAPSHOT='43bb8773224773960c5f9e7a7d8235213fd5fdbec9a5cec59a0e0f074d9b070e'
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,x):(P/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
NOTES={
'JNC 7 guideline':'Se identifica el documento histórico por su título oficial en PubMed y la traducción española de OPS. Guía JNC 7 es una denominación abreviada del informe; no se presenta como guía vigente.',
'JNC 8 report':'JNC 8 se identifica como el informe de los miembros del panel nombrado para ese comité; no se inventa una autoría institucional distinta ni se sustituye su fecha por la de una guía actual.',
'guideline-driven management':'La forma inglesa exacta está en el título de Carey et al. en Circulation Research. La expresión española manejo basado en las guías de práctica clínica está en el consenso SIAC; se verifica lenguaje general de manejo, no una indicación farmacológica concreta.',
'evidence-based review':'Revisión basada en la evidencia está atestada en el objetivo de una evaluación oficial de ARA-II. No se supone que cualquier revisión basada en evidencia sea necesariamente una revisión sistemática.',
'ten-year ASCVD risk':'La fuente española AHA identifica explícitamente la calculadora de enfermedad cardiovascular aterosclerótica y el horizonte de los próximos 10 años en el mismo párrafo. No se sustituye por riesgo cardiovascular total ni por riesgo a 30 años.',
'primordial prevention':'Ambas fuentes AHA distinguen evitar la aparición de factores de riesgo de la prevención primaria una vez presentes esos factores.',
'CARDIA study':'La narrativa española AHA identifica la cohorte longitudinal Coronary Artery Risk Development in Young Adults, iniciada en 1985-86. Se rechaza la coincidencia con el ensayo CARDia sobre angioplastia/cirugía en diabetes y la referencia inglesa aislada de la bibliografía SEC.',
'REGARDS study':'El diseño original inglés y la narrativa española SEC identifican la misma cohorte REasons for Geographic And Racial Differences in Stroke, no una intervención aleatorizada.',
'NHANES':'La página oficial española de CDC desarrolla el nombre de la encuesta y conserva NHANES. Se reemplaza la coincidencia anterior localizada solo en bibliografía inglesa.',
'co-chair':'Copresidente aparece en una comunicación oficial de OMS; el cargo compartido es equivalente a co-chair. No se aprueba automáticamente la variante coordinador conjunto.',
'renin-independent aldosterone production':'El caso y discusión publicados en español dicen producción autónoma de aldosterona independiente de la actividad de renina. Se eligió esta formulación específica de producción, en vez de depender solo de secreción.',
'hypokalemic metabolic alkalosis':'El título y resumen de Nefrología atestan alcalosis metabólica hipopotasémica. La asociación clínica del caso con Gitelman no convierte Gitelman ni Bartter en sinónimos de la alteración bioquímica.',
'medication titration':'La fuente SEC atesta titulación de dosis y describe cambios de medicación, aumentos y reducciones según respuesta/tolerancia. La redacción preferida ajuste gradual de la dosis conserva ese proceso; no se limita a aumentar dosis.',
'mineralocorticoid receptor antagonist therapy':'MR se expande en la publicación como receptor mineralocorticoide; tratamiento con antagonistas del MR corresponde a la terapia de esa clase, sin aprobar una molécula, dosis ni indicación para todo paciente.',
'subclinical atherosclerosis':'La fuente española SEC usa aterosclerosis subclínica para enfermedad identificada por imagen. No se equipara a enfermedad cardiovascular clínica sintomática.',
'sodium-containing salts':'Salts containing sodium y sales de sodio designan la clase química, incluyendo sales distintas del cloruro sódico. No se asumen equivalencia de formulaciones, carga de sodio ni dosis.',
'alcohol moderation':'El pasaje inglés de ESC recomienda restrict alcohol consumption; la fuente española usa moderación del consumo de alcohol. Se verifica la acción de limitar consumo, no simplemente la categoría epidemiológica consumo moderado.',
'micrograms per day':'Micrograms/day y mcg/24h expresan masa por día. Un día equivale a 24 h; no se añade una conversión de dosis ni se trasladan intervalos de referencia del estudio histórico.',
'micrograms per deciliter':'MedlinePlus español define expresamente Mcg/dL = microgramos por decilitro. µg y mcg son representaciones de microgramo; dL no se confunde con L ni con volumen por día.',
'clinical guidelines implementation':'El estudio primario español identifica implementación de guías de práctica clínica. La guía inglesa usa guideline implementation. No se fusiona la implementación con mera publicación o conocimiento de una guía.',
'arterial compliance':'Se ajusta la preferencia española a compliancia arterial, forma atestada en una publicación de la Academia Nacional de Medicina. Distensibilidad arterial no se conserva como equivalencia automática universal; la corrección se limita al dataset de investigación.',
'hybrid sphygmomanometer':'El protocolo oficial CCSS clasifica esfigmomanómetros manuales e incluye expresamente los aneroides y los híbridos. No se confunde híbrido con todo dispositivo automático oscilométrico.',
'attended automated office blood pressure':'La definición española de PA automatizada en consulta dice con asistencia de un profesional de la salud o sin él. Se selecciona específicamente la modalidad con asistencia; se sustituye el fragmento anterior con o sin personal, que por sí solo era ambiguo.',
'renal parenchymal hypertension':'El artículo inglés atesta la denominación causal completa. La traducción SEC dice hipertensión por enfermedad renal parenquimatosa y renovascular. El extractor pega la conjunción y al adjetivo; esa grafía pegada se conserva solo como forma localizada y no como español recomendado. Las dos etiologías siguen separadas.',
'adrenal lateralization':'El texto español describe lateralización en la secreción de aldosterona entre las dos suprarrenales. No se equipara a la técnica de muestreo venoso ni a lateralidad anatómica sin función hormonal.',
'lateralizing primary aldosteronism':'Lateralizing PA y HAP que lateraliza identifican predominio funcional de producción en una suprarrenal. No se equipara a todo nódulo unilateral por imagen.',
'overnight dexamethasone suppression test':'La referencia clínica española distingue la prueba nocturna con un miligramo de la prueba de dos días y describe administración nocturna y medición a la mañana siguiente. No se verificó solo el término genérico prueba de dexametasona ni se exportó un protocolo de dosificación.',
'preoperative alpha blockade':'Ambos textos conservan bloqueo alfa y su momento preoperatorio en feocromocitoma/paraganglioma. La atestación del caso no demuestra necesidad universal ni eficacia de una pauta.',
'licorice-induced hypertension':'El caso inglés y el capítulo español identifican hipertensión causada por ingestión de regaliz; no se convierte toda ingestión en diagnóstico de hipertensión ni se fusiona con aldosteronismo primario.',
'albumin excretion rate':'La fuente española incluye explícitamente tasa de excreción de albúmina, no solo excreción de albúmina. Se conserva la dimensión temporal y su distinción del cociente albúmina/creatinina.',
'spot urine sample':'El informe español distingue muestra de orina aislada de una recogida nocturna o cronometrada; que se prefiera matinal no convierte toda muestra aislada en primera orina de la mañana.',
'biochemical adherence testing':'El pasaje español describe pruebas bioquímicas de concentración de medicación en suero/orina para evaluar adherencia. La guía inglesa habla de chemical adherence testing. No se usa control de PA, glucemia o HbA1c como prueba de ingestión.',
'alcohol-mediated renal denervation':'Ambas fuentes identifican alcohol como agente de denervación renal. No se confunde con moderación del consumo de alcohol, radiofrecuencia ni ultrasonido; no se infiere beneficio clínico por el nombre del procedimiento.',
'renal artery stenting':'La colocación de un stent arterial está descrita en el contexto explícito de arteriografía y tratamiento de la arteria renal en MedlinePlus. No se confunde con angioplastia sin stent ni con un stent ureteral.',
'asymptomatic markedly elevated blood pressure':'La revista española usa la denominación completa y la distingue de emergencia con daño orgánico agudo. Se ajusta la redacción preferida a asintomática, en vez de sin síntomas como requisito literal absoluto. La evaluación de daño agudo y los umbrales dependen del contexto; una cifra aislada no define emergencia.',
'focal neurological deficit':'MedlinePlus atesta déficit neurológico focal como disminución de función neurológica. Se sustituye el apoyo insuficiente lesiones neurológicas focales: lesión anatómica y déficit funcional no son equivalencias automáticas.',
'intravenous antihypertensive therapy':'La administración de medicamentos intravenosos aparece en el apartado de descenso de PA en emergencias hipertensivas y contrasta con tratamiento antihipertensivo oral. El contexto conserva el fin antihipertensivo; no se aprueba cualquier medicación intravenosa como alias.',
'flash pulmonary edema':'La publicación española tiene la palabra clave edema pulmonar flash junto a flash pulmonary oedema. La redacción preferida de aparición súbita explica flash; no equivale a cualquier edema pulmonar crónico.',
'postpartum preeclampsia':'Las páginas paralelas de MedlinePlus nombran preeclampsia que aparece o persiste tras el parto. No se reduce a hipertensión posparto sin los demás criterios de preeclampsia.',
'perinatal death':'La fuente española utiliza muerte perinatal en una nota de resultados, no una tasa de mortalidad perinatal. No se redefine el periodo perinatal ni se fusiona muerte fetal y muerte neonatal.',
'glomerular hypertension':'El artículo inglés identifica hipertensión capilar glomerular por su denominación exacta. Se deja de depender del fragmento arteriolar de la figura; la fuente española atesta hipertensión glomerular.',
'blood pressure percentile':'El estudio inglés usa blood pressure percentile. El consenso español refiere el percentil 95 del promedio de PA domiciliaria según sexo y talla. Se verifica el concepto percentil de PA, no un percentil de talla confundido con la presión.',
'cerebral hypoperfusion':'La publicación usa palabras clave bilingües explícitas hipoperfusión cerebral / cerebral hypoperfusion. No se infiere infarto, hemorragia ni déficit neurológico a partir de hipoperfusión.',
'intermittent hypoxemia':'La lista de palabras clave del mismo artículo empareja intermittent hypoxemia e hipoxemia intermitente, y además lista hipoxia intermitente por separado. No se fusiona hipoxemia sanguínea con hipoxia tisular.',
'CLICK trial':'El artículo primario inglés identifica CLICK; el texto español de Favaloro usa ensayo CLICK en ERC avanzada y clortalidona. No se contó la palabra informática click ni otro ensayo de la misma clase.',
'BPROAD trial':'El registro primario y la narrativa SEC identifican Blood Pressure Control Target in Diabetes / BPROAD. Se conserva la denominación internacional y se verifica la identidad de la intervención de PA, no una recomendación clínica para toda diabetes.',
'ESPRIT trial':'ESPRIT se localiza en el cuerpo español sobre ensayos de control de PA, no solo en el glosario ni la bibliografía. La identidad se coteja con el ensayo de la guía inglesa.',
'Advance-HTN trial':'El resumen ACC y la sección española de Ateroma identifican Advance-HTN, fase 2b con lorundrostat. Se eligió la página de contenido, no el índice, y se separó del ensayo SOUL adyacente con semaglutida.',
'HYVET trial':'El nombre inglés Hypertension in the Very Elderly Trial y la narrativa española estudio HYVET identifican el mismo ensayo. HYVET-COG no se añade como alias de todo HYVET.',
'ASCOT-BPLA trial':'ASCOT-BPLA aparece en el texto español de la monografía SEC; se conserva específicamente el brazo de reducción de PA y no se fusiona con ASCOT-LLA.',
'RADIANCE-HTN TRIO trial':'Se reemplaza la referencia bibliográfica inglesa de la versión española por la narrativa estudio RADIANCE-HTN TRIO en la revisión española publicada. TRIO sigue separado de SOLO y RADIANCE II.',
'SPYRAL HTN-OFF MED trial':'La narrativa española identifica estudio SPYRAL HTN-OFF MED en pacientes sin antihipertensivos. No se usa solo una referencia inglesa ni se fusiona OFF MED con ON MED.',
'standard blood pressure control':'Tratamiento estándar en la fuente SEC está definido como el brazo de control de PA comparado con control intensivo en BPROAD. Se descarta la primera coincidencia en otro contexto terapéutico; no se fija un objetivo universal a partir del ensayo.',
'nonfatal stroke':'ACV no mortal y nonfatal stroke conservan el desenlace no fatal. No se fusiona con muerte por ictus ni con el compuesto cardiovascular completo.',
'odds ratio':'El diccionario español oficial del NCI enumera razón de momios como denominación de la medida. Se resuelve el préstamo inglés insuficiente; no se añaden automáticamente todos los sinónimos del diccionario ni se confunde con RR o HR.',
'2021 KDIGO blood pressure guideline':'El resumen oficial inglés de KDIGO y la traducción española de PQRAD identifican por título completo la guía de PA de 2021. No se confunde con la guía de diabetes ni con la guía general de ERC de 2024.',
'2024 KDIGO CKD guideline':'El PDF oficial inglés y la portada del resumen español identifican la guía KDIGO 2024 para evaluación y manejo de ERC. La fecha del alojamiento no sustituye al año del documento.',
}
# Reviewed replacement localizers, avoiding English-only Spanish bibliography hits.
# Tuple: source ID, attested form, one-based locator (None = locate in this source).
PINS={
'JNC 7 guideline':{'es':('S146','Séptimo Informe del Comité Nacional Conjunto',1)},
'guideline-driven management':{'en':('S188','Guideline-Driven Management',2)},
'ten-year ASCVD risk':{'es':('S150','riesgo actual de enfermedad cardiovascular aterosclerótica',3)},
'CARDIA study':{'es':('S156','estudio de CARDIA',3)},
'NHANES':{'en':('S188','NHANES',3),'es':('S143','NHANES',2)},
'renin-independent aldosterone production':{'es':('S190','producción autónoma de aldosterona, independiente de la actividad de renina',None)},
'medication titration':{'es':('S191','titulación de dosis',None)},
'alcohol moderation':{'en':('S71','restrict alcohol consumption',13)},
'micrograms per deciliter':{'es':('S182','microgramos por decilitro',3)},
'arterial compliance':{'es':('S136','compliancia arterial',1)},
'Advance-HTN trial':{'es':('S145','ADVANCE-HTN',110)},
'ESPRIT trial':{'es':('S29','ESPRIT',71)},
'RADIANCE-HTN TRIO trial':{'es':('S184','estudio RADIANCE-HTN TRIO',2)},
'SPYRAL HTN-OFF MED trial':{'es':('S184','estudio SPYRAL HTN-OFF MED',4)},
'standard blood pressure control':{'es':('S131','tratamiento estándar',3)},
'odds ratio':{'es':('S148','razón de momios',1)},
'2021 KDIGO blood pressure guideline':{'en':('S04','KDIGO 2021 Clinical Practice Guideline',1)},
}
CORRECTIONS={
'arterial compliance':('distensibilidad arterial','compliancia arterial','Preferencia española más precisa, atestada; no se declara sinonimia universal con distensibilidad.'),
'asymptomatic markedly elevated blood pressure':('presión arterial marcadamente elevada sin síntomas','presión arterial marcadamente elevada asintomática','Denominación técnica atestada; se añade contexto de ausencia de daño orgánico agudo y se evita interpretar sin síntomas como exclusión de todo síntoma inespecífico.'),
}
def main():
 assert hashlib.sha256((P/'session3_discovery.json').read_bytes()).hexdigest()==SNAPSHOT,'New snapshot requires new editorial review.'
 hits=read('session3_discovery.json'); assert len(hits)==57 and {h['en'] for h in hits}==NOTES.keys()
 corpus={s['source_id']:s for s in read('source_cache/corpus.json')}
 now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
 records=[];decisions=[];corrections=[]
 for h0 in hits:
  h=copy.deepcopy(h0);name=h['en'];assert h['en_hit'] and h['es_hit']
  if name in CORRECTIONS:
   before,after,reason=CORRECTIONS[name];assert h['es']==before;h['es']=after
   corrections.append(dict(id=h['id'],canonical_en=name,field='preferred_es',previous=before,corrected=after,reason=reason,scope='research_dataset_only',original_and_candidate_modified=False,reviewed_at_utc=now))
  for lang,(sid,form,index) in PINS.get(name,{}).items():
   s=corpus[sid]
   if index is None:
    found=find([form],list(map(norm,s['pages'])));assert found,(name,lang,sid,form)
    index=found['page_pdf']
   h[lang+'_hit']=dict(source_id=sid,form=form,url=s['url'],locator_kind=s['locator_kind'],locator_index=index)
  a,b=h['en_hit'],h['es_hit']
  literal=norm(name)==norm(a['form']) and norm(h['es'])==norm(b['form'])
  rec=dict(id=h['id'],canonical_en=name,preferred_es=h['es'],category=h['category'],en_attestation=a,es_attestation=b,method='literal_pair' if literal else 'reviewed_terminological_variant_or_contextual_rendering',en_canonical_verbatim_normalized=norm(name)==norm(a['form']),es_preferred_verbatim_normalized=norm(h['es'])==norm(b['form']),editorial_note=NOTES[name],reviewed_by='assistant',reviewed_at_utc=now,verification_session='session3',independent_clinician_review='not_performed',automatic_substitution_approved=False)
  for lang in ['en','es']:
   att=rec[lang+'_attestation'];s=corpus[att['source_id']];page=s['pages'][att['locator_index']-1]
   assert s['language']==lang or (s['locator_kind']=='indexed_bilingual_author_keywords' and lang in s['language'].split(','))
   assert ' '+norm(att['form'])+' ' in ' '+norm(page)+' ',(name,lang,att)
   assert not (lang=='es' and att['source_id']=='S29' and att['locator_index']>=92),(name,'English bibliography')
   att.update(source_copy_sha256=s['sha256'],extracted_locator_sha256=hashlib.sha256(page.encode('utf-8')).hexdigest(),locator_index_is_pdf_page=s['locator_kind']=='pdf_page')
  if name=='asymptomatic markedly elevated blood pressure':
   rec['supplementary_context_sources']=[dict(source_id='S189',locator_kind=corpus['S189']['locator_kind'],locator_index=1,scope='Official AHA Spanish severe-hypertension/no-listed-symptoms distinction; not the sole proof of the complete label.')]
  records.append(rec)
  decisions.append(dict(id=h['id'],canonical_en=name,preferred_es=h['es'],decision='accepted_external_bilingual_crosscheck',reviewer='assistant_editorial_review',independent_clinician_review='not_performed',reason=NOTES[name],reviewed_at_utc=now,verification_session='session3'))
 assert len(records)==len({r['id'] for r in records})==57
 save('session3_verification.json',dict(schema_version='1.0',updated_at_utc=now,input_discovery_sha256=SNAPSHOT,scope='Final 57 canonical EN/preferred ES terminology pairs; assistant editorial review only, no runtime integration.',counts=dict(verified=57,pending=0,preferred_es_corrections=2),records=records))
 save('session3_review_decisions.json',dict(reviewed_at_utc=now,input_discovery_sha256=SNAPSHOT,policy='Explicit assistant review of this fixed snapshot. Future string matches are not approved by this script.',decisions=decisions))
 save('session3_terminology_corrections.json',dict(updated_at_utc=now,corrections=corrections))
 print('57 pairs reviewed; 2 Spanish preferences corrected in research only. Baseline 600 untouched.')
if __name__=='__main__':main()

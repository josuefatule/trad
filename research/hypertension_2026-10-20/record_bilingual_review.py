"""Record the assistant's editorial review of a fixed discovery snapshot.

This is a frozen review decision, not an automatic approval rule for future hits.
No clinical certification or runtime export is performed.
"""
import json, hashlib, datetime as dt
from pathlib import Path
from verify_bilingual import norm, find_corpus
P=Path(__file__).resolve().parent
def read(n): return json.loads((P/n).read_text(encoding='utf-8'))
def write(n,v): (P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
EXPECTED='30466d380bd89f66876400c031e421ebce25ac1ba4a4b75f5875b5f1cf2681cd'
# The final snapshot includes the two subsequently reviewed PubMed abstracts.
SNAPSHOT_COUNTS=(657,609)
EXCLUDED={
 'focal neurological deficit':'Lesiones neurológicas focales no atesta déficit neurológico focal; se conserva pendiente.',
 'spot urine sample':'Una muestra de la mañana no verifica la equivalencia general de muestra aislada o puntual.',
 'odds ratio':'La forma inglesa prestada odds ratio no atesta la traducción propuesta razón de momios.',
 'albumin excretion rate':'Excreción de albúmina sin tasa no conserva la dimensión temporal de excretion rate.',
 'arterial compliance':'Distensibilidad y compliance requieren distinguir el cambio absoluto de volumen del cambio relativo; pendiente una equivalencia precisa.',
 'attended automated office blood pressure':'El pasaje español con o sin observador reúne dos modalidades; falta atestación específica de la modalidad con observador.',
 'glomerular hypertension':'El localizador inglés especifica arteriolar; se retiene para revisar el compartimento vascular con una fuente más precisa.',
 'NHANES':'La coincidencia española encontrada es una referencia bibliográfica inglesa, no una atestación narrativa en español.',
 'alcohol moderation':'Se retiene la expresión de intervención para un cotejo más literal; el pasaje inglés localizado describe consumo moderado y sus límites.',
}
NOTES={
 '2017 ACC/AHA guideline':'El anuncio oficial AHA identifica la guía previa de 2017 y su reemplazo; la denominación corta se resuelve por ese contexto.',
 'plasma aldosterone concentration':'El pasaje español de laboratorio usa aldosterona plasmática como magnitud medida; no se trata de secreción ni producción.',
 'urinary potassium excretion':'Excreción renal de potasio se refiere aquí a la salida urinaria en el consenso KDIGO sobre homeostasis del potasio.',
 'extracellular fluid volume':'Volumen extracelular corresponde al compartimento de líquido extracelular en el párrafo fisiológico.',
 'potassium-rich diet':'La frase inglesa atesta una dieta DASH rica en potasio, ejemplo explícito de dieta rica en potasio; DASH no se añade como alias estricto.',
 'potassium-enriched salt substitute':'La recomendación española menciona sustituir sodio por sal rica en potasio; no se equipara cualquier sal potásica con un sustituto comercial específico.',
 'renal perfusion pressure':'Presión de perfusión aparece en el contexto inmediato de la estenosis de arterias renales y activación del SRAA.',
 'vascular fibrosis':'La lista española fibrosis miocárdica, renal y vascular comparte el sustantivo fibrosis con el modificador vascular.',
 'oscillometric blood pressure measurement':'El párrafo de técnica de medición dice que las técnicas oscilométricas miden la PA de forma no invasiva.',
 'cuff bladder':'Bladder y cámara de aire aparecen en las instrucciones de longitud y anchura del manguito, no en anatomía urinaria.',
 'cuff inflation':'Inflation e inflado se refieren al manguito en la técnica de medición de PA del mismo apartado.',
 'blood pressure telemonitoring':'La telemonitorización se describe en el manejo y automedida de PA; el calificador se recupera del párrafo.',
 '24-hour average blood pressure':'Los pasajes hablan de medias de PA de día, noche y 24 h; el registro conserva exclusivamente la media de 24 h.',
 'night-to-day blood pressure ratio':'El cociente noche-día se define dentro de la medición ambulatoria de PA; no es un cociente de otra magnitud.',
 'unattended automated office blood pressure':'Sin médicos o personal presente define la modalidad automatizada sin observador en el apartado de PA en consulta.',
 'creatinine-cystatin C estimated glomerular filtration rate':'eGFRcr-cys es la sigla de TFGe basada en creatinina y cistatina C; se conserva la combinación, no solo una de las sustancias.',
 'sodium-glucose cotransporter 2 inhibitors':'SGLT2 y su expansión se identifican en los glosarios de la guía; no se confunden con inhibidores SGLT1.',
 'nonsteroidal mineralocorticoid receptor antagonist':'ARM se expande en la guía española como antagonistas del receptor de mineralocorticoides; se mantiene no esteroideos.',
 'kidney disease progression':'El contexto es progresión de ERC; no se infiere equivalencia entre progresión renal y cualquier descenso transitorio de TFGe.',
 'pill burden':'Número de pastillas es el título y medida de carga farmacológica en el apartado de adherencia; no significa dosis farmacológica total.',
 'multidisciplinary team-based care':'La atención multidisciplinaria se define como colaboración entre profesionales complementaria a la atención médica regular.',
 'ultrasound renal denervation':'La lista española incluye radiofrecuencia y ultrasonido como modalidades distintas; se selecciona la modalidad por ultrasonido.',
 'retinal hemorrhages':'El párrafo de fondo de ojo enumera retinal exudates, haemorrhages, or papilloedema; retinal tiene alcance sobre la lista. La fuente SEC atesta hemorragias retinianas.',
 'silent cerebral infarcts':'Infartos silentes aparece en el apartado de daño cerebral identificado por RM; no se verifica mediante microinfartos como equivalencia de cualquier tamaño.',
 'cerebral microbleeds':'Microbleeds y microhemorragias pertenecen al daño cerebral por RM en el mismo esquema; el contexto recupera cerebral.',
 'chronic hypertension in pregnancy':'Hipertensión preexistente está definida dentro del embarazo; no se equipara cualquier hipertensión crónica fuera de ese contexto.',
 'soluble fms-like tyrosine kinase-1':'Se cotejó el biomarcador sFlt-1 completo con tirosina cinasa 1 soluble similar a fms del glosario ESC de embarazo; no es PlGF.',
 'number needed to harm':'Cochrane atesta número necesario para dañar, pero recomienda expresar NNT para un resultado perjudicial adicional; conservar esta nota de preferencia.',
 'dose escalation':'El aumento de dosis se interpreta como escalada en el algoritmo terapéutico; no certifica pauta ni dosis concretas.',
 'sham procedure':'Sham tiene sentido de intervención simulada dentro de los ensayos de procedimientos; no es un procedimiento activo.',
 'SCORE2':'Nombre internacional del modelo conservado en el glosario español y la guía inglesa.',
 'SCORE2-OP':'Nombre internacional del modelo para personas mayores conservado en ambas versiones; no se fusiona con SCORE2.',
 'SCORE2-Diabetes':'Nombre internacional del modelo específico de diabetes conservado en ambas versiones.',
}
def main():
 if (P/'session3_verification.json').exists():
  raise SystemExit('Historical 600-pair review is frozen. Use the session3 review and finalize_657.py.')
 assert hashlib.sha256((P/'bilingual_discovery.json').read_bytes()).hexdigest()==EXPECTED, 'Discovery changed; a new editorial review is required.'
 hits=read('bilingual_discovery.json')
 assert (len(hits),sum(bool(h['en_hit'] and h['es_hit']) for h in hits))==SNAPSHOT_COUNTS
 corpus=read('source_cache/corpus.json')
 for s in corpus: s['normalized_pages']=list(map(norm,s['pages']))
 # The first Spanish matches for four drugs were English bibliography entries.
 # Replace them with actual Spanish medication lists, reviewed in the AHA page.
 for h in hits:
  if h['en'] in ['ramipril','candesartan','olmesartan','irbesartan']:
   hit=find_corpus([h['es']], [s for s in corpus if s['source_id']=='S80'],'es')
   assert hit, h['en']; h['es_hit']=hit
 now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
 decisions=[]; accepted=[]
 for h in hits:
  both=bool(h['en_hit'] and h['es_hit'])
  ok=both and h['en'] not in EXCLUDED
  reason=EXCLUDED.get(h['en']) or (NOTES.get(h['en']) if ok else None)
  if not reason:
   reason=('Equivalencia terminológica revisada por el asistente; se conservaron entidad, método, modalidad, temporalidad y calificadores clínicos.' if ok else 'No se obtuvo atestación individual suficiente en ambos idiomas; no se infiere verificación del mero respaldo temático.')
  decision=dict(id=h['id'],canonical_en=h['en'],preferred_es=h['es'],decision='accepted_external_bilingual_crosscheck' if ok else 'pending',reviewer='assistant_editorial_review',independent_clinician_review='not_performed',reason=reason)
  decisions.append(decision)
  if ok:
   a,b=h['en_hit'],h['es_hit']
   literal=(norm(h['en'])==norm(a['form']) and norm(h['es'])==norm(b['form']))
   rec=dict(id=h['id'],canonical_en=h['en'],preferred_es=h['es'],category=h['category'],en_attestation=a,es_attestation=b,method='literal_pair' if literal else 'reviewed_terminological_variant_or_contextual_rendering',en_canonical_verbatim_normalized=norm(h['en'])==norm(a['form']),es_preferred_verbatim_normalized=norm(h['es'])==norm(b['form']),editorial_note=reason,reviewed_by='assistant',reviewed_at_utc=now,independent_clinician_review='not_performed',automatic_substitution_approved=False)
   for lang in ['en','es']:
    att=rec[lang+'_attestation']; s=next(s for s in corpus if s['source_id']==att['source_id'])
    assert s['language']==lang
    page=s['pages'][att['locator_index']-1]
    assert ' '+norm(att['form'])+' ' in ' '+norm(page)+' '
    att['source_copy_sha256']=s['sha256']
    att['extracted_locator_sha256']=hashlib.sha256(page.encode('utf-8')).hexdigest()
    att['locator_index_is_pdf_page']=s['locator_kind']=='pdf_page'
   accepted.append(rec)
 assert len(accepted)==600
 input_sha=hashlib.sha256((P/'bilingual_discovery.json').read_bytes()).hexdigest()
 write('bilingual_decisions.json',dict(schema_version='1.0',reviewed_at_utc=now,input_discovery_sha256=input_sha,policy='Frozen assistant editorial decisions on this snapshot; future string matches are not automatically approved.',counts=dict(reviewed_records=657,discovery_pairs=609,accepted=600,pending=57,rejected_discovery_pairs=9),decisions=decisions))
 write('bilingual_verification.json',dict(schema_version='1.0',updated_at_utc=now,scope='Canonical EN↔preferred ES terminology only. No automatic alias approval, clinical certification, ASR evaluation, or runtime integration.',normalization='Unicode NFKD, casefold, accent-insensitive punctuation/token normalization and PDF line-break joining. Exact matched forms retained.',locator_policy='PDF page is one-based. Other indices are one-based blocks in the locally extracted source corpus; original titles and author keywords are explicitly labeled.',counts=dict(verified=600,pending=57),records=accepted))
 print('Editorial decisions: 600 accepted; 57 pending; 9 discovery pairs excluded.')
if __name__=='__main__': main()

"""Apply explicit research-only editorial decisions to a frozen alias inventory.

No production imports, operational exports or writes to the canonical dataset.
Lexical discovery is kept separate from editorial review and external approval.
"""
import copy,datetime as dt,hashlib,json,re
from collections import Counter,defaultdict
from pathlib import Path
from prepare_alias_audit import tokens,sha
P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# These exceptions were reviewed individually against the complete inventory.
# They supersede generic lexical/abbreviation handling and retain raw provenance.
EXCEPTIONS=[
 ('hypertension','hipertenso','exclude_strict_equivalence','Es adjetivo o persona; conservar hipertenso/hipertensa según la frase, sin convertirlo en el nombre de la enfermedad.'),
 ('hypertension','hypertensive','exclude_strict_equivalence','Adjetivo o sustantivo de persona; no sustituir por hypertension. Mantener separado en una propuesta gramatical.'),
 ('normotension','normotenso','exclude_strict_equivalence','Persona o adjetivo frente a estado fisiológico; no sustituir por normotensión.'),
 ('normotension','normotensive','exclude_strict_equivalence','Adjetivo/persona frente a nombre de estado; conservar categoría gramatical.'),
 ('JNC 8 report','Eighth Joint National Committee','exclude_strict_equivalence','Comité y documento no son la misma entidad. Usar JNC 8 report para el informe; retener el comité solo como entidad relacionada.'),
 ('co-chair','coordinador conjunto','exclude_strict_equivalence','La coordinación conjunta no garantiza el cargo de copresidente. Mantener copresidente; no promover el cargo alternativo a alias.'),
 ('diuretics','diuretic therapy','exclude_strict_equivalence','Clase de fármacos frente a tratamiento. Conservar diuretic therapy como expresión relacionada: tratamiento con diuréticos.'),
 ('frailty','frail patients','exclude_strict_equivalence','Condición frente a grupo de personas. Conservar frail patients como pacientes con fragilidad, sin colapsarlo con frailty.'),
 ('pill burden','carga de medicación','exclude_strict_equivalence','Carga de medicación es más amplia que número de comprimidos. Proponer número de comprimidos/pastillas como aclaración contextual; no sustituir por dosis total.'),
 ('sympathetic activation','hiperactividad simpática','exclude_strict_equivalence','La activación no implica necesariamente hiperactividad. Conservar activación simpática; hiperactividad queda relacionada con un grado de actividad aumentado.'),
 ('pressure natriuresis','relación presión-natriuresis','exclude_strict_equivalence','El fenómeno y su relación o curva de respuesta no son cadenas intercambiables. Mantener la relación como expresión relacionada.'),
 ('blood pressure classification','blood pressure categories','contextual_equivalence','Categorías y sistema de clasificación se relacionan, pero no designan el mismo objeto en toda frase; preservar estructura de clasificación.'),
 ('systolic blood pressure','presión sistólica','contextual_equivalence','Exige contexto de presión arterial; no completar automáticamente si se trata de una cavidad o circuito pulmonar.'),
 ('systolic blood pressure','systolic pressure','contextual_equivalence','Exige contexto de presión arterial; no añadir el territorio arterial sistémico a una medida de otra localización.'),
 ('diastolic blood pressure','presión diastólica','contextual_equivalence','Exige contexto arterial; puede describir otra presión diastólica si se elimina la localización.'),
 ('diastolic blood pressure','diastolic pressure','contextual_equivalence','Conservar el territorio de medición; arterial no se debe inferir de diastolic aislado.'),
 ('home blood pressure monitoring','automedición domiciliaria de la presión arterial','contextual_equivalence','Forma clínica de AMPA; verificar quién mide y el ámbito domiciliario. No equiparar todo seguimiento remoto o medición por un profesional con automedición.'),
 ('cardiovascular risk','riesgo de enfermedad cardiovascular','contextual_equivalence','Exige el mismo desenlace y horizonte temporal; no completar ASCVD, diez años ni una ecuación concreta.'),
 ('cardiovascular risk','cardiovascular disease risk','contextual_equivalence','Conservar desenlace y horizonte; el riesgo cardiovascular genérico no identifica por sí solo una calculadora.'),
 ('renin suppression','suppressed renin','contextual_equivalence','Proceso de supresión frente a hallazgo de renina suprimida; conservar tiempo, mecanismo y construcción de la oración.'),
 ('renin suppression','renina suprimida','contextual_equivalence','Hallazgo frente a proceso; no inferir prueba de supresión ni diagnóstico de aldosteronismo.'),
 ('extracellular fluid volume','extracellular volume','contextual_equivalence','Expresión abreviada válida cuando el compartimento es líquido; no extender a todo volumen extracelular de una técnica de imagen.'),
 ('extracellular fluid volume','volumen extracelular','contextual_equivalence','Requiere contexto de líquido extracelular; mantener el compartimento y la técnica de medición.'),
 ('antihypertensive medication','blood pressure medication','contextual_equivalence','Expresión de divulgación; confirmar que reduce la PA. No inferir fármaco ni indicación a partir de una referencia genérica a presión arterial.'),
 ('medication adherence','treatment adherence','contextual_equivalence','Adherencia al tratamiento puede incluir dieta, ejercicio u otras intervenciones. Conservar el calificador farmacológico cuando es el objeto.'),
 ('medication titration','dose titration','contextual_equivalence','Ajuste de dosis de una medicación en este contexto; no presupone aumento, fármaco concreto o pauta.'),
 ('thiazide diuretics','thiazide-type diuretics','contextual_equivalence','La extensión varía por autor: KDIGO 2012 lo usa como grupo amplio que incluye thiazide-like. No mapear universalmente a tiazidas estructurales; conservar el término del documento y sus ejemplos.'),
 ('cardiac arrhythmia','arrhythmia','contextual_equivalence','La abreviación lexical requiere contexto cardíaco; no ampliar a un diagnóstico o subtipo específico.'),
 ('obstructive sleep apnea','síndrome de apnea obstructiva del sueño','contextual_equivalence','Mantener la palabra síndrome cuando aparece; no convertir un evento de apnea aislado en síndrome ni perder el carácter obstructivo.'),
 ('lifestyle modification','manejo del estilo de vida','contextual_equivalence','Manejo incluye evaluación y seguimiento; modificación designa cambio. Conservar como expresión relacionada bajo contexto, no sustitución literal.'),
 ('lifestyle modification','lifestyle management','contextual_equivalence','Manejo y modificación tienen alcance distinto; no convertir seguimiento o consejo en modificación ya realizada.'),
 ('healthy diet','healthy dietary pattern','contextual_equivalence','Patrón y dieta son formulaciones relacionadas en recomendaciones; no convertirlo en un régimen específico como DASH.'),
 ('dietary sodium restriction','sodium restriction','contextual_equivalence','Exige contexto de ingesta dietética; no reemplazar una restricción en otro medio o procedimiento.'),
 ('potassium-enriched salt substitute','potassium-supplemented salt','contextual_equivalence','Confirmar que se usa como sustituto de sal y conserva la composición del producto; no inferir porcentaje o dosis de potasio.'),
 ('sugar-sweetened beverages','sugary drinks','contextual_equivalence','Forma coloquial; verificar presencia de azúcar añadido en la definición del estudio. No incluir automáticamente bebidas sin azúcar añadido.'),
 ('aerobic exercise','aerobic training','contextual_equivalence','Entrenamiento es un programa; ejercicio puede ser una actividad aislada. Conservar duración y modalidad.'),
 ('dynamic resistance exercise','dynamic resistance training','contextual_equivalence','Programa de entrenamiento frente a ejercicio; conservar dinámico y de fuerza, sin inferir resistencia aeróbica.'),
 ('dynamic resistance exercise','ejercicio dinámico de resistencia','contextual_equivalence','Resistencia se usa aquí como fuerza contra carga; no confundir con resistencia cardiorrespiratoria.'),
 ('isometric resistance exercise','isometric resistance training','contextual_equivalence','Conservar isométrico y la diferencia entre ejercicio y programa de entrenamiento.'),
 ('isometric resistance exercise','ejercicio de resistencia isométrica','contextual_equivalence','Conservar contracción isométrica de fuerza; no convertir en ejercicio dinámico o aeróbico.'),
 ('plasma concentration','plasma levels','contextual_equivalence','Niveles es una expresión informal de concentración solo si el analito y la muestra son explícitos; no inferir actividad de renina.'),
 ('plasma concentration','niveles plasmáticos','contextual_equivalence','Confirmar analito, muestra y magnitud; niveles no implica actividad ni unidades concretas.'),
 ('oscillometric blood pressure monitor','oscillometric device','contextual_equivalence','Dispositivo oscilométrico es más amplio fuera del contexto de PA; conservar el tipo de medida.'),
 ('inter-arm blood pressure difference','inter-arm difference','contextual_equivalence','Expresión elíptica: exigir que la diferencia sea de PA, no de circunferencia u otra medida.'),
 ('clinical guidelines implementation','guideline implementation','contextual_equivalence','Exige guías de práctica clínica, sin inferir una guía o versión concreta.'),
 ('systemic vascular resistance','peripheral vascular resistance','contextual_equivalence','Uso fisiológico contextual; preservar circulación sistémica. No confundir resistencia vascular pulmonar ni expandir PVR sin definición.'),
 ('systemic vascular resistance','resistencia vascular periférica','contextual_equivalence','Validar circulación sistémica y magnitud; periférica no autoriza inferir territorio pulmonar.'),
 ('daytime blood pressure','awake blood pressure','contextual_equivalence','Periodo del reloj y vigilia no son idénticos. Usar diario de sueño y definición del protocolo; no intercambiar automáticamente en trabajadores por turnos.'),
 ('nighttime blood pressure','asleep blood pressure','contextual_equivalence','Noche y sueño pueden diferir. Usar diario/protocolo y conservar el periodo informado.'),
 ('night-to-day blood pressure ratio','relación noche-día','contextual_equivalence','Exigir PA y sentido noche/día; no invertir numerador y denominador ni inferir porcentaje de descenso.'),
 ('adrenal venous sampling','cateterismo de venas suprarrenales','contextual_equivalence','El cateterismo es el acceso; confirmar muestreo de sangre suprarrenal. No equiparar una intervención venosa sin toma de muestras con AVS.'),
 ('dual combination therapy','biterapia antihipertensiva','contextual_equivalence','Exige contexto antihipertensivo y dos componentes; no asumir un único comprimido.'),
 ('triple combination therapy','triterapia antihipertensiva','contextual_equivalence','Exige contexto antihipertensivo y tres componentes; no asumir dosis fija o un único comprimido.'),
 ('therapeutic inertia','clinical inertia','contextual_equivalence','La literatura usa ambos términos de forma intercambiable en falta de inicio/intensificación indicada. Retener en ese contexto; no atribuir inercia a toda ausencia de cambio terapéutico.'),
 ('multidisciplinary team-based care','atención multidisciplinaria','contextual_equivalence','Varios profesionales no prueban trabajo coordinado en equipo. Mantener el atributo de equipo cuando es parte del modelo.'),
 ('left atrial enlargement','dilatación de la aurícula izquierda','contextual_equivalence','Confirmar medida de tamaño/volumen auricular y criterio de la técnica; no inferir hipertrofia, fibrilación o umbral.'),
 ('double-blind trial','double-masked trial','contextual_equivalence','Variantes de enmascaramiento: conservar a quién se ocultó la asignación; doble no identifica por sí solo los dos grupos.'),
 ('2025 AHA/ACC guideline','2025 ACC/AHA guideline','contextual_equivalence','El orden de las sociedades puede variar; mantener año y tema de hipertensión. En 2025 existen otras guías AHA/ACC, incluida ACS.'),
]

# External meanings that were checked specifically in this audit (not internal duplicates).
EXTERNAL=[
 ('PA','primary aldosteronism (en)','presión arterial (es)', ['S10','S29'],'Mantener idioma y definición local; el idioma solo no basta para toda acepción.'),
 ('HRV','heart rate variability (en)','hipertensión renovascular (es)',['AS18','S29'],'Exigir expansión local y especialidad; no transportar la sigla entre idiomas.'),
 ('RAR','reducción absoluta del riesgo (es)','ratio aldosterona-renina (es)',['AS16','S29'],'Exigir medida y unidades; no decidir solo por idioma. S93 usa RRA, que no justifica atestar RAR.'),
 ('ARR','aldosterone-to-renin ratio (en)','absolute risk reduction (en)',['S71','AS11'],'Distinguir endocrinología y medida de efecto; conservar sigla si no se define.'),
 ('PRA','plasma renin activity','panel reactive antibody',['S10','AS06'],'Distinguir endocrinología y evaluación inmunológica del trasplante.'),
 ('PAC','plasma aldosterone concentration','premature atrial contraction',['AS17','AS05'],'Distinguir analito y evento electrocardiográfico.'),
 ('ACS','autonomous cortisol secretion','acute coronary syndrome',['S10','AS07'],'Distinguir endocrinología y síndrome coronario; no resolver mediante frecuencia de uso.'),
 ('FMD','fibromuscular dysplasia','flow-mediated dilation',['AS19','AS08'],'Distinguir enfermedad vascular y medición funcional endotelial.'),
 ('IAH','índice de apnea-hipopnea (es)','intra-abdominal hypertension (en)',['S29','AS09'],'Exigir idioma, expansión y magnitud; no colapsar índice y enfermedad.'),
 ('PEG','pequeño para la edad gestacional (es)','percutaneous endoscopic gastrostomy (en)',['S98','AS10'],'Distinguir clasificación de tamaño y procedimiento digestivo.'),
 ('CI','confidence interval','cardiac index',['S71','AS12'],'Distinguir intervalo estadístico y medida hemodinámica; conservar unidades.'),
 ('RR','relative risk','respiratory rate',['AS20','AS13'],'Distinguir medida de efecto y signo vital; no expandir por proximidad de números.'),
 ('IC','intervalo de confianza','insuficiencia cardíaca',['S64','S98'],'La misma lengua y especialidad pueden contener ambas acepciones; exigir definición local.'),
 ('HR','heart rate','hazard ratio',['S41','S05'],'Distinguir frecuencia cardíaca de razón de riesgos instantáneos; no decidir por números aislados.'),
 ('MR','mineralocorticoid receptor','magnetic resonance',['S17','S188'],'Distinguir receptor y técnica de imagen; no completar MR angiography como receptor.'),
 ('RAS','renin-angiotensin system','renal artery stenosis',['S71','AS15'],'Distinguir sistema hormonal y lesión de arteria renal; ambas acepciones existen en hipertensión.'),
]

def main():
 stamp=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
 data=read('hypertension_research_en_es.json');inv=read('alias_inventory.json');discovery=read('alias_evidence_discovery.json')
 assert sha(P/'hypertension_research_en_es.json')==inv['input_dataset_sha256']=='bdcb40eea6c84e20ff327859eeac23f3b3194b3de9cfdd5553d6444e99e588c2'
 cm={c['id']:c for c in data['concepts']};byname={c['canonical_en']:c for c in data['concepts']}
 occurrences={f['occurrence_id']:f for f in inv['occurrences']};colliding={m.get('occurrence_id') for g in inv['collisions'] for m in g['members'] if m.get('occurrence_id')}
 overrides={(c,f):(status,note) for c,f,status,note in EXCEPTIONS}
 assert len(overrides)==len(EXCEPTIONS)
 assert overrides.keys()<={(r['canonical_en'],r['form']) for r in discovery['records']}
 short_forms={}
 for c in data['concepts']:
  for a in c['abbreviations']:short_forms[(c['id'],a['language'],a['form'])]=a
 # Short forms absent from the old abbreviation list, reviewed in this pass.
 extra_short={'aTRH','eGFR','Ang I','Ang-(1-7)','AT1 receptor','AT2 receptor','mGFR','eGFRcr','eGFRcr-cys','SGLT2 inhibitors','iSGLT2','sFlt-1','ITT analysis','overnight DST','dihydropyridine CCBs','non-dihydropyridine CCBs','nonsteroidal MRA','ARM no esteroideo'}
 reviews=[]
 for r in discovery['records']:
  c=cm[r['concept_id']];k=(c['id'],r['language'],r['form']);roles=r['roles'];form=r['form']
  specific=overrides.get((c['canonical_en'],form))
  if specific:status,note=specific
  elif any(i in colliding for i in r['occurrence_ids']):
   status='collision_requires_explicit_definition';note='Colisión entre conceptos del inventario. Retener únicamente con definición local; no elegir expansión por precedencia del archivo.'
  elif c['category']=='units_measurement' and c['canonical_en'] in {'millimeters of mercury','milligrams per day','milligrams per deciliter','millimoles per day','micrograms per day','micrograms per deciliter','nanograms per deciliter'}:
   status='unit_symbol_preserve';note='Conservar valor, unidad, prefijo, barra y denominador. Admitir grafía equivalente solo con análisis dimensional; esta revisión no convierte cantidades ni dosis.'
  elif k in short_forms or form in extra_short or re.search(r'\b(?:BP|AOBP|CT|TC|CCBs|ACE|AT[12]|PREVENT)\b',form):
   status='abbreviation_context_only';note='Forma abreviada o fórmula: exigir definición local, idioma y concepto; conservar número gramatical, subíndices y calificadores. No aprobar expansión automática.'
  elif tokens(form)==tokens(c['canonical_en'] if r['language']=='en' else c['preferred_es']):
   status='orthographic_variant';note='Difiere en grafía, puntuación o tildes bajo la normalización de comparación; conservar la forma original en la oración. La coincidencia no autoriza alterar símbolos o valores.'
  elif (form.rstrip('s')==c['canonical_en'].rstrip('s')) and r['language']=='en':
   status='inflection_preserve_number';note='Flexión de número; conservar singular/plural y concordancia en la frase.'
  else:
   status='lexical_variant_for_research';note='Revisión editorial: variante de denominación utilizable para consulta dentro de este concepto; conservar gramática y todos los calificadores. No es autorización de sustitución literal.'
  scope_evidence=[dict(kind='canonical_pair_context_only',verification_record_id=c['id'],file='bilingual_verification.json',supports_alias_surface=False)]
  if r['literal_location']:scope_evidence.append(dict(kind='literal_surface_location_only',**r['literal_location']))
  reviews.append(dict(**r,status=status,editorial_reason=note,evidence=scope_evidence,external_surface_attestation='normalized_literal_location_not_semantic_approval' if r['literal_location'] else 'no_literal_location_in_searched_corpus',not_literally_attested_form_requires_targeted_source_before_strict_alias=not bool(r['literal_location']),automatic_substitution_approved=False,reviewed_by='assistant',independent_clinician_review='not_performed',reviewed_at_utc=stamp))
 # Expansion proposals are overlays. Never rewrite the inherited objects.
 fixes=[]
 def fix(concept,form,lang,expansion,reason):
  c=byname[concept];a=short_forms[(c['id'],lang,form)]
  fixes.append(dict(correction_id=f'AE{len(fixes)+1:03}',concept_id=c['id'],canonical_en=concept,form=form,language=lang,field='abbreviations.expansion',previous=a['expansion'],proposed=expansion,reason=reason,source_ids=['S29'] if lang=='es' else list(c['review']['translation_crosscheck_source_ids']),basis='explicit_glossary_definition' if lang=='es' else 'editorial_grammatical_number_proposal_with_class_context',action='research_proposal_only_not_applied',automatic_substitution_approved=False))
 fix('home blood pressure monitoring','AMPA','es','automedida de la presión arterial','Restituir auto-medición en la expansión de AMPA; el término genérico de monitorización domiciliaria no expande sus letras. S29, glosario, usa automedida de la presión arterial por parte del paciente.')
 fix('obstructive sleep apnea','SAOS','es','síndrome de apnea obstructiva del sueño','Restituir síndrome; la expansión heredada omitía la S. No inferir diagnóstico por un episodio de apnea.')
 for concept,form,exp in [('mineralocorticoid receptor antagonists','MRA','mineralocorticoid receptor antagonist'),('angiotensin II receptor blockers','ARB','angiotensin II receptor blocker'),('calcium channel blockers','CCB','calcium channel blocker'),('nonsteroidal anti-inflammatory drugs','NSAID','nonsteroidal anti-inflammatory drug')]:
  fix(concept,form,'en',exp,'Proponer expansión singular para esta forma sin s; conservar el plural como variante separada. El número final siempre depende de la oración, pues algunas fuentes usan la sigla sin flexión para la clase.')
 # Clean evidence metadata, without treating vague earlier notes as verified meanings.
 meaning_edits=[]
 for c in data['concepts']:
  for a in c['abbreviations']:
   previous=a.get('other_meanings',[])
   if not previous:continue
   own=tokens(a['expansion']);retained=[];removed=[];unverified=[]
   for m in previous:
    clean=re.sub(r'\s*\((?:EN|ES)\).*$', '',m,flags=re.I)
    if tokens(clean)==own or (a['form']=='MRA' and m=='mineralocorticoid receptor antagonist') or (c['canonical_en']=='randomized controlled trial' and m=='ensayo controlado aleatorizado'):
     removed.append(dict(value=m,reason='Es la propia expansión o su variante de número, no otra acepción.'))
    elif any(s in m for s in ['algunos discursos','varias sociedades','otras abreviaturas']):
     unverified.append(dict(value=m,reason='Descripción vaga o plural inferido sin acepción y fuente específicas; retirar del campo de significados verificados.'))
    else:retained.append(m)
   if removed or unverified:meaning_edits.append(dict(concept_id=c['id'],form=a['form'],language=a['language'],previous=previous,proposed_distinct_meanings=retained,remove_self_expansions=removed,demote_to_unverified_notes=unverified,policy='Retained historical alternatives are context warnings; only the separate evidence register marks specifically checked external meanings.',action='research_proposal_only_not_applied'))
 # A near spelling pair is reviewed as distinct, even at very high similarity.
 near=[]
 for i,pair in enumerate(discovery['near_form_screen'],1):
  pair=copy.deepcopy(pair);pair.update(review_id=f'NP{i:03}',decision='keep_distinct_do_not_fuzzy_merge',reason='Los conceptos conservan calificadores o magnitudes diferentes: polaridad, cifra, localización, modalidad, clase, fecha, objetivo frente a lectura o identidad de estudio. La similitud de caracteres no establece equivalencia; las relaciones de inclusión tampoco autorizan sustitución.',evidence_record_ids=[pair['concept_a'],pair['concept_b']],automatic_substitution_approved=False);near.append(pair)
 # Protect compound reference names even when they have no alias list.
 reference_labels=[]
 for c in data['concepts']:
  if any(s in c['canonical_en'] for s in [' trial',' study','guideline','report','SCORE2','PREVENT','NHANES','DASH diet']):
   reference_labels.append(dict(concept_id=c['id'],label=c['canonical_en'],decision='retain_complete_reference_identity',reason='Conservar año, rama, protocolo y nombre; no reducir a una sigla genérica compartida.',automatic_substitution_approved=False))
 # Cross-source homographs do not create more canonical concepts or internal collisions.
 external=[dict(form=f,inventory_meaning=a,competing_meaning=b,source_ids=s,decision='definition_required_keep_unexpanded_if_unclear',correction=n,internal_collision=False) for f,a,b,s,n in EXTERNAL]
 identity_cases=[
  dict(label='CARDIA / CARDia',inventory_reference='CARDIA study',competing_reference='Coronary Artery Revascularisation in Diabetes trial',source_ids=['S156','AS03'],decision='keep_different_studies',correction='No resolver por mayúsculas ni convertir la cohorte en el ensayo; exigir nombre desarrollado, diseño o registro.'),
  dict(label='STEP / STEP-1',inventory_reference='STEP trial',competing_reference='Semaglutide Treatment Effect in People with Obesity STEP-1',source_ids=['S71'],decision='retain_trial_suffix_and_protocol',correction='S71, glosario PDF 6, enumera ambos. Conservar población e intervención; no eliminar -1.'),
 ]
 guards=[]
 guardmap=copy.deepcopy(data['do_not_merge'])
 guardmap.update({'first morning urine sample':['spot urine sample'],'intermittent hypoxemia':['intermittent hypoxia'],'plasma renin activity':['direct renin concentration'],'serum potassium':['plasma potassium'],'angiotensin-converting enzyme':['angiotensin-converting enzyme 2'],'sodium chloride':['potassium chloride'],'lateralizing primary aldosteronism':['aldosterone-producing adenoma','adrenal lateralization','adrenal computed tomography'],'adrenal venous sampling':['adrenal computed tomography'],'single-pill combination':['fixed-dose combination','polypill'],'ten-year ASCVD risk':['10-year cardiovascular disease risk'],'thiazide diuretics':['thiazide-like diuretics'],'arterial compliance':['arterial distensibility'],'sham procedure':['sham-controlled trial'],'kidney failure':['renal insufficiency','chronic kidney disease']})
 for a,bs in guardmap.items():
  for b in bs:
   guards.append(dict(a=a,b=b,a_concept_id=byname[a]['id'] if a in byname else None,b_concept_id=byname[b]['id'] if b in byname else None,decision='related_or_distinct_not_unconditional_alias',reason='Conservar alcance, magnitud, método, muestra, subtipo y calificadores. Algunas relaciones son de inclusión o solapamiento, no de entidades disjuntas. No colapsar por semejanza o pertenencia.',source_basis='canonical_verification_and_inherited_do_not_merge_context',automatic_substitution_approved=False))
 prior_risks=[]
 for f,meanings in data['cross_language_abbreviation_ambiguities'].items():
  if f not in {e['form'] for e in external} and f not in {'MRA','ECA'}:
   prior_risks.append(dict(form=f,historical_meanings=meanings,status='retained_historical_warning_not_all_secondary_meanings_reverified',instruction='No expandir sin definición; no presentar cada significado heredado como verificado en esta sesión.'))
 perconcept=[]
 for c in data['concepts']:
  rs=[r for r in reviews if r['concept_id']==c['id']]
  perconcept.append(dict(concept_id=c['id'],canonical_en=c['canonical_en'],preferred_es=c['preferred_es'],review_status='completed_editorial_safety_audit',form_ids=[r['form_id'] for r in rs],alternative_occurrence_count=sum(len(r['occurrence_ids']) for r in rs),unique_alternative_form_count=len(rs),no_alternative_forms=not bool(rs),canonical_pair_verification_unchanged=True,automatic_substitution_approved=False,scope='All inventoried alternatives reviewed. Empty lists mean no additional forms, not missing review. Canonical labels were screened as collision targets and retain qualifiers.'))
 counts=dict(concepts_reviewed=len(perconcept),concepts_with_alternatives=sum(not c['no_alternative_forms'] for c in perconcept),concepts_without_alternatives=sum(c['no_alternative_forms'] for c in perconcept),alternative_occurrences=len(inv['occurrences']),unique_concept_language_forms=len(reviews),by_status=dict(Counter(r['status'] for r in reviews)),literal_surface_locations=sum(bool(r['literal_location']) for r in reviews),forms_without_literal_surface_location=sum(not r['literal_location'] for r in reviews),internal_collision_groups=len(inv['collisions']),external_homograph_warnings_checked=len(external),near_form_pairs_reviewed=len(near),expansion_correction_proposals=len(fixes),other_meanings_metadata_correction_proposals=len(meaning_edits),reference_labels_protected=len(reference_labels),automatic_substitutions_approved=0,editorial_audit_pending_concepts=0,editorial_audit_pending_occurrences=0)
 counts.update(reference_identity_collision_cases=len(identity_cases),clinical_distinction_pairs=len(guards))
 save('alias_review_decisions.json',dict(schema_version='1.0',reviewed_at_utc=stamp,input_dataset_sha256=inv['input_dataset_sha256'],input_inventory_sha256=sha(P/'alias_inventory.json'),review_scope='Research safety and equivalence assessment, not independent clinical certification or individual external verification of every surface form.',counts=counts,form_reviews=reviews,concept_coverage=perconcept,expansion_correction_proposals=fixes,other_meanings_metadata_corrections=meaning_edits,internal_collisions=inv['collisions'],external_homographs=external,historical_warnings_not_reverified=prior_risks,near_form_decisions=near,reference_identity_guards=reference_labels,reference_identity_collision_cases=identity_cases,clinical_distinction_guards=guards))
 print(json.dumps(counts,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

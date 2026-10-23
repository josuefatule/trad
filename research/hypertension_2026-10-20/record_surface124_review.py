"""Record reviewed source selections for the 124 previously unattested surfaces.

Selections below are editorial decisions, not automatic acceptance of search hits.
No canonical, original, candidate, or previous alias-review file is rewritten.
"""
import json,hashlib,datetime as dt,re
from pathlib import Path
from urllib.parse import urlparse
from collections import Counter
from verify_bilingual import norm
P=Path(__file__).resolve().parent
APPROVED_DISCOVERY_SHA='70cd933b883212e104680e3017a184868479c69607079e4016d2207e52ec83d0'
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# One specifically reviewed source for each selected surface. A URL fragment is
# used only to identify the full URL already returned by the research tools.
SELECTIONS={
 'UF0038':'10.64221/aem-38-1-2026-004',
 'UF0042':'clinicbarcelona.org/asistencia/enfermedades/hipertension-arterial/diagnostico-y-pruebas',
 'UF0044':'pubmed.ncbi.nlm.nih.gov/17173814/',
 'UF0058':'physicians.wustl.edu/the-new-high-in-blood-pressure/',
 'UF0075':'1313%20Hypertension20presentation20ACC20MEVirani.pdf',
 'UF0079':'learn.acc.org/Page/LEARNHTN',
 'UF0083':'pmc.ncbi.nlm.nih.gov/articles/PMC10396066/',
 'UF0117':'apps.who.int/gb/ebwha/pdf_files/EB111/seb11129.pdf',
 'UF0148':'sciencedirect.com/science/article/pii/S1889183702712300',
 'UF0157':'pubmed.ncbi.nlm.nih.gov/24569125/',
 'UF0158':'iris.who.int/bitstream/handle/10665/38534/9241542357_eng_part1.pdf',
 'UF0159':'pubmed.ncbi.nlm.nih.gov/8544895/',
 'UF0174':'Hypertension_Highlights_Detailed_Summary_ucm_497446.pdf',
 'UF0175':'pubmed.ncbi.nlm.nih.gov/7804949/',
 'UF0196':'pubmed.ncbi.nlm.nih.gov/1980236/',
 'UF0205':'pubmed.ncbi.nlm.nih.gov/17651686/',
 'UF0206':'iris.who.int/bitstream/handle/10665/43847/9789243547282_spa.pdf',
 'UF0207':'Guidelines_Made_Simple_2017_HBP.pdf',
 'UF0232':'who.int/news-room/fact-sheets/detail/stroke',
 'UF0247':'professional.heart.org/en/science-news/2023-acc-aha-accp-hrs-guideline-for-the-diagnosis-and-management-of-atrial-fibrillation',
 'UF0267':'professional.heart.org/en/science-news/dietary-diversity-implications-for-obesity-prevention-in-adult-populations/Commentary',
 'UF0274':'scielo.isciii.es/pdf/medif/v13n4/notacli1.pdf',
 'UF0277':'pmc.ncbi.nlm.nih.gov/articles/PMC10595026/',
 'UF0280':'Sugary-Drink-Definition-2025.pdf',
 'UF0281':'newsroom.heart.org/news/seguir-9-pasos-clave-para-una-vida-de-alimentacion-saludable-puede-reforzar-la-salud-cardiovascular',
 'UF0282':'pubmed.ncbi.nlm.nih.gov/35252853/',
 'UF0286':'dspace.uce.edu.ec/bitstreams/3f9611e4-ec06-47fd-9f86-6e8cec120ab1/download',
 'UF0288':'pubmed.ncbi.nlm.nih.gov/16434724/',
 'UF0289':'pubmed.ncbi.nlm.nih.gov/26081765/',
 'UF0295':'emro.who.int/world-health-days/2013/control-factsheet-2013.html',
 'UF0304':'pubmed.ncbi.nlm.nih.gov/23889806/',
 'UF0305':'pubmed.ncbi.nlm.nih.gov/39366028/',
 'UF0306':'scielo.isciii.es/pdf/nefrologia/v33n5/original_breve.pdf',
 'UF0308':'applications.emro.who.int/imemrf/Urol_Ann/Urol_Ann_2015_7_2_259_261.pdf',
 'UF0309':'pubmed.ncbi.nlm.nih.gov/26975712/',
 'UF0313':'pubmed.ncbi.nlm.nih.gov/19609054/',
 'UF0315':'Libraries-with-Heart-packet-English-and-Spanish.pdf',
 'UF0317':'estandares-e-indicadores-para-la-acreditacion-de-hospitales-en-america-latina-y-el-caribe.pdf',
 'UF0336':'scielo.org.mx/scielo.php?pid=S0186-48662018000200006',
 'UF0337':'kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-Blood-Pressure-Guideline-English.pdf',
 'UF0345':'pubmed.ncbi.nlm.nih.gov/32310535/',
 'UF0349':'pubmed.ncbi.nlm.nih.gov/29034226/',
 'UF0356':'pubmed.ncbi.nlm.nih.gov/18426445/',
 'UF0369':'iris.paho.org/bitstream/handle/10665.2/52998/9789275322987_spa.pdf',
 'UF0370':'iris.paho.org/bitstream/10665.2/52467/4/v44e882020.pdf',
 'UF0372':'pubmed.ncbi.nlm.nih.gov/10624754/',
 'UF0373':'pubmed.ncbi.nlm.nih.gov/23344133/',
 'UF0375':'intramed.net/content/tecnologias-de-apoyo-para-mejorar-el-abordaje-de-la-hipertension-arterial',
 'UF0381':'pubmed.ncbi.nlm.nih.gov/25167742/',
 'UF0384':'pubmed.ncbi.nlm.nih.gov/28834120/',
 'UF0387':'pid=S2254-28842019000200151',
 'UF0388':'pubmed.ncbi.nlm.nih.gov/29866740/',
 'UF0389':'scielo.org.mx/pdf/acm/v72n1/v72n1a12.pdf',
 'UF0390':'msps.es/gl/estadEstudios/estadisticas/normalizacion/clasifEnferm/boletines/Codificacion_clinica_n13_99.pdf',
 'UF0391':'revistamedicinainterna.uy/index.php/smiu/libraryFiles/downloadPublic/3',
 'UF0396':'pubmed.ncbi.nlm.nih.gov/36517385/',
 'UF0399':'pubmed.ncbi.nlm.nih.gov/1740499/',
 'UF0406':'medlineplus.gov/spanish/pruebas-de-laboratorio/prueba-de-tsh/',
 'UF0408':'extranet.who.int/ncdccs/Data/COL_D1_DIABETES_TIPO_1_COMPLETA.pdf',
 'UF0410':'pubmed.ncbi.nlm.nih.gov/27315758/',
 'UF0411':'nefrologiaaldia.org/articulo/hiperaldosteronismo-primario/',
 'UF0412':'pubmed.ncbi.nlm.nih.gov/8544895/',
 'UF0417':'pubmed.ncbi.nlm.nih.gov/26654388/',
 'UF0424':'extranet.who.int/ncdccs/Data/PRY_D1_Manual%20Manejo%20ECV-2013.pdf',
 'UF0426':'pubmed.ncbi.nlm.nih.gov/38374860/',
 'UF0427':'pubmed.ncbi.nlm.nih.gov/10786365/',
 'UF0434':'professional.heart.org/en/guidelines-and-statements/prevent-calculator',
 'UF0435':'scielo.isciii.es/scielo.php?lng=es&nrm=iso&pid=S0211-69952016000100003',
 'UF0437':'pubmed.ncbi.nlm.nih.gov/24798667/',
 'UF0438':'pubmed.ncbi.nlm.nih.gov/41760262/',
 'UF0440':'bestpractice.bmj.com/topics/es-es/875',
 'UF0460':'pubmed.ncbi.nlm.nih.gov/1706990/',
 'UF0461':'journals.sagepub.com/doi/10.1345/aph.1L610',
 'UF0467':'pubmed.ncbi.nlm.nih.gov/38532223/',
 'UF0471':'farmaceuticoscomunitarios.org/es/journal-article/propuesta-adecuacion-presentacion-del-medicamento-dosis-pautada-evitando-fracciones',
 'UF0472':'pubmed.ncbi.nlm.nih.gov/25947275/',
 'UF0478':'saha.org.ar/uploads/pdf/1757093403.pdf',
 'UF0480':'pubmed.ncbi.nlm.nih.gov/10583722/',
 'UF0481':'scielo.isciii.es/scielo.php?lng=es&nrm=iso&pid=S0365-66912004000900007',
 'UF0483':'pubmed.ncbi.nlm.nih.gov/27250996/',
 'UF0486':'pubmed.ncbi.nlm.nih.gov/28720207/',
 'UF0487':'sahta.com/docs/librosCasosClinicos/libroCasosClinicos_2019.pdf',
 'UF0490':'cochrane.org/es/evidence/CD004351_prevention-and-treatment-postpartum-hypertension',
 'UF0491':'BRN-MN-32-02-OPERATIONALGUIDANCE-2012-eng-Hyptensive-Pregnancy-Disorder-Management-Protocol.pdf',
 'UF0492':'pubmed.ncbi.nlm.nih.gov/32965939/',
 'UF0493':'pubmed.ncbi.nlm.nih.gov/31169958/',
 'UF0497':'pubmed.ncbi.nlm.nih.gov/31056598/',
 'UF0498':'pubmed.ncbi.nlm.nih.gov/11305141/',
 'UF0501':'iris.who.int/bitstream/handle/10665/138405/9789243548333_spa.pdf',
 'UF0504':'cochrane.org/es/evidence/CD012269_antithrombotic-therapy-prevent-cognitive-decline-people-small-vessel-disease-neuroimaging-without',
 'UF0505':'iris.who.int/bitstream/10665/70935/4/ICD_10_1970_v2_spa_2.pdf',
 'UF0507':'pubmed.ncbi.nlm.nih.gov/20189027/',
 'UF0515':'pubmed.ncbi.nlm.nih.gov/21250065/',
 'UF0516':'extranet.who.int/ncdccs/Data/CHL_B4_Programa-de-salud-cardiovascular.-MINSAL-Chile-2017.pdf',
 'UF0518':'acc.org/latest-in-cardiology/ten-points-to-remember/2021/09/02/18/37/summary-international-consensus-statement',
 'UF0524':'pubmed.ncbi.nlm.nih.gov/32119297/',
 'UF0527':'acc.org/about-acc/press-releases/2024/05/21/16/00/early-diagnosis-treatment-of-peripheral-artery-disease-essential-to-improve-outcomes-reduce-amputation-risk',
 'UF0529':'cdn.who.int/media/docs/default-source/wash-documents/wash-chemicals/chloride.pdf',
 'UF0530':'pubmed.ncbi.nlm.nih.gov/33747305/',
 'UF0533':'pubmed.ncbi.nlm.nih.gov/19811552/',
 'UF0539':'iris.who.int/bitstream/handle/10665/161913/9789243547671_spa.pdf',
 'UF0540':'pubmed.ncbi.nlm.nih.gov/21347435/',
 'UF0541':'1313-Hypertension20presentation20ACC20MEVirani.pdf',
 'UF0546':'pubmed.ncbi.nlm.nih.gov/21897887/',
 'UF0547':'pubmed.ncbi.nlm.nih.gov/380910/',
 'UF0548':'pubmed.ncbi.nlm.nih.gov/26537937/',
 'UF0550':'jaccjacc.acc.org/Clinical_Document/Cholesterol_GL_Web_Supplement.pdf',
 'UF0551':'tools.acc.org/LDL/index.html',
 'UF0556':'pubmed.ncbi.nlm.nih.gov/38620441/',
 'UF0557':'pubmed.ncbi.nlm.nih.gov/40467132/',
 'UF0558':'pubmed.ncbi.nlm.nih.gov/42486643/',
 'UF0562':'pubmed.ncbi.nlm.nih.gov/38110039/',
 'UF0564':'iris.who.int/bitstream/handle/10665/365174/9789240063181-spa.pdf',
 'UF0566':'extranet.who.int/ncdccs/Data/MEX_D1_GER_TaquicardiaSupraventricular.pdf',
}

NOTES={
 'UF0015':'No se localizó una atestación literal aceptable. Farmacológica no expresa de manera inequívoca inducida por fármacos y puede confundirse con tratamiento farmacológico. Proponer retirada del alias estricto; conservar hipertensión inducida por fármacos.',
 'UF0038':'Uso español explícito sobre dispersión/variación de la PA; no inferir una métrica concreta de variabilidad a partir de tensional.',
 'UF0044':'El título original español de PubMed atesta la frase completa. Se mantiene la distinción entre automedición, medición por otra persona y telemonitorización.',
 'UF0058':'La comunicación de la facultad de medicina usa two en lugar de 2. Conservar guía, fecha y definición; la grafía no fija un umbral universal.',
 'UF0075':'Título abreviado de la guía de hipertensión de 2017 en diapositivas de ACC. Su existencia no confirma vigencia clínica actual ni autoriza suprimir el año.',
 'UF0079':'La página educativa oficial de ACC usa la expresión en el manejo de hipertensión. No confundir management con una recomendación, fármaco o pauta particular.',
 'UF0117':'Atestada en OMS para un cargo de coordinación FAO/OMS. No demuestra copresidencia. Se reconfirma la exclusión como alias estricto de co-chair.',
 'UF0148':'Atestada en confirmación de aldosteronismo; la carga y el protocolo diagnóstico no son el mismo concepto. Exigir vía y contexto; no inferir oral frente a infusión.',
 'UF0206':'La fuente OMS usa el nombre de tratamiento; no se usan aquí sus recomendaciones ni se generaliza una indicación a toda sustitución hormonal.',
 'UF0267':'AHA emplea la frase para patrón alimentario. Conservar patrón/dieta y no asignarle automáticamente DASH u otro régimen.',
 'UF0277':'Frase localizada en una publicación de comentario clínico alojada en PMC, que resume un metaanálisis. Apoyo limitado; no se promueve a atestación primaria ni a sustitución estricta del producto sin conocer su composición.',
 'UF0280':'La definición oficial de AHA relaciona la expresión con bebidas con azúcares añadidos. Retener el alcance de la definición; no añadir zumos sin azúcar agregado por semejanza verbal.',
 'UF0286':'La frase exacta aparece en una tabla de una tesis institucional, no se confirmó en una publicación clínica primaria seleccionada. Se conserva como evidencia limitada de uso; no se declara verificación externa suficiente.',
 'UF0304':'Unidad literal de microgramos por día en un resumen de investigación. La observación de la unidad no valida la dosis del estudio ni habilita conversiones de fármaco.',
 'UF0305':'mcg/day aparece como unidad de folato en un resumen de investigación; la unidad no depende del fármaco ni de una indicación antihipertensiva.',
 'UF0306':'Símbolo en texto español de nefrología. μ y µ se cotejan por normalización Unicode, sin convertir microgramos en miligramos.',
 'UF0308':'Unidad en inglés de concentración en un artículo alojado por OMS/EMRO. El alojamiento no lo convierte en una recomendación de la OMS.',
 'UF0309':'Símbolo de unidad independiente del idioma. Se registra una atestación en fuente inglesa; no se presenta como prosa española. Se conserva el prefijo micro y el denominador dL.',
 'UF0313':'Expresión atestada para analitos plasmáticos. Exigir analito y magnitud: levels no equivale siempre a concentración ni a actividad de renina.',
 'UF0317':'Término en especificaciones de equipamiento de OPS. No se deduce que un modelo particular esté validado por el nombre del dispositivo.',
 'UF0336':'Atestación de la relación fisiológica presión-natriuresis. El proceso y la relación/curva no se sustituyen literalmente; se mantiene la exclusión estricta previa.',
 'UF0345':'La fuente desarrolla SVR como resistencia vascular sistémica. Conservar territorio sistémico y no inferir resistencia pulmonar.',
 'UF0349':'Definición inglesa de HRV comprobada. La acepción española hipertensión renovascular documentada antes sigue siendo competidora; exigir definición local.',
 'UF0372':'La fuente usa la medida de PA en vigilia. Su existencia no iguala vigilia a horario diurno; conservar diario de sueño y periodo del protocolo.',
 'UF0373':'La fuente usa la medida de PA durante el sueño. No intercambiar automáticamente con noche, particularmente con horarios de sueño desplazados.',
 'UF0375':'Solo se seleccionó una traducción/resumen profesional secundario para la frase completa; su uso se registra como hallazgo limitado, sin promoverlo a fuente primaria ni a sinonimia estricta.',
 'UF0384':'Atestado como patrón nocturno de ascenso/reversed dipping; no sustituir por descenso normal o ausencia de descenso.',
 'UF0387':'La relación se refiere a PA nocturna/diurna en el artículo. No invertir numerador y denominador ni convertir la razón en porcentaje de descenso.',
 'UF0388':'Sigla explícita de hipertensión refractaria en investigación. No intercambiar con hipertensión resistente o aparentemente resistente.',
 'UF0390':'Atestación literal en documento institucional español de codificación histórica. Solo prueba denominación; no se usan sus códigos ni sus clasificaciones como actuales.',
 'UF0391':'Frase española localizada en material publicado por la sociedad/revista de medicina interna uruguaya; la detección no equivale al diagnóstico de una causa secundaria.',
 'UF0396':'Palabras clave bilingües de PubMed atestan la denominación. Cateterizar las venas no demuestra por sí solo que se haya realizado muestreo hormonal suficiente.',
 'UF0399':'El resumen define DST como prueba de supresión con dexametasona y usa overnight DST. No eliminar horario, dosis o protocolo al expandir.',
 'UF0406':'MedlinePlus identifica tirotropina con TSH. No se usa la coincidencia tirotropina alfa de un producto recombinante como equivalencia del analito nativo.',
 'UF0410':'El consenso usa el nombre de hiperaldosteronismo remediable con glucocorticoides dentro de formas familiares. No extender a todo hiperaldosteronismo.',
 'UF0411':'Capítulo de Nefrología al Día atesta la forma española en hiperaldosteronismo familiar tipo I. Conservar subtipo y no extrapolar tratamiento a otras causas.',
 'UF0424':'El manual sitúa la frase en la fila de causas secundarias renovasculares (tabla 13). Es una coincidencia literal con otra finalidad diagnóstica; no verifica la prueba de desafío/supresión para aldosteronismo. Exigir propósito y protocolo antes de usar la variante.',
 'UF0426':'El título del artículo vincula explícitamente Gordon y pseudohypoaldosteronism type II. No colapsar con tipo I o enfermedad de Addison.',
 'UF0427':'El título original español de PubMed hace explícita la relación con síndrome de Gordon; conservar el tipo II y no corregir seudo- a hipoaldosteronismo sin el prefijo.',
 'UF0434':'La página oficial PREVENT desarrolla UACR como razón albúmina/creatinina urinaria. No convertir en proteína/creatinina ni en excreción de albúmina por unidad de tiempo.',
 'UF0438':'El resumen define UPCR como razón proteína/creatinina urinaria. No usar UACR como sustituto.',
 'UF0440':'La forma española fue localizada en una referencia clínica BMJ. No se revalidan umbrales; conservar categoría y referencia a albúmina.',
 'UF0460':'Denominación torasemide atestada en publicación farmacológica; se conserva identidad del principio activo, sin inferir equivalencia de dosis o formulación.',
 'UF0461':'El editor ofrece resumen español explícito que usa clevidipina y resumen inglés del mismo artículo para clevidipine. Se mantiene clevidipino como preferencia previa; no se infiere licencia ni pauta.',
 'UF0471':'El artículo de farmacéuticos usa carga para la preparación/llenado de sistemas de dosificación. No atesta carga de comprimidos como carga de medicación. Se reconfirma la retirada del alias estricto de pill burden.',
 'UF0478':'Forma exacta en un documento de SAHA. Se conserva agudo; daño crónico o hipertensión severa sin daño agudo no son equivalentes.',
 'UF0487':'Caso clínico de sociedad de hipertensión describe el edema de aparición brusca. Mantener la rapidez de inicio y no convertir todo edema pulmonar en flash.',
 'UF0491':'Frase en protocolo nacional de embarazo alojado por OMS; se identifica como documento nacional. Posparto y preeclampsia posparto no son diagnósticos intercambiables.',
 'UF0492':'La fuente define FGR; no confundir con SGA/PEG como simple tamaño para la edad gestacional.',
 'UF0493':'El bloque Other abstract español de PubMed desarrolla RCF. Se distingue de FGR inglés y de PEG. El acceso directo posterior estuvo restringido; la atestación procede del resumen indexado explícitamente español.',
 'UF0497':'Título en español y palabras clave bilingües de un estudio de casos y controles: nacimiento pretérmino. No se redefine edad gestacional ni se elimina el calificador pretérmino.',
 'UF0498':'El título original español de PubMed usa plaquetopenia; el título inglés correspondiente identifica thrombocytopenia. Se descartan como evidencia española las coincidencias portuguesas.',
 'UF0501':'La guía OMS española relaciona aspirina con ácido acetilsalicílico. La atestación del término no avala una dosis ni indicación actual.',
 'UF0505':'El índice institucional español contiene atrofia encefálica. Uso histórico exclusivamente terminológico, sin usar codificación antigua ni inferir causa de la atrofia.',
 'UF0515':'Examen de fondo ocular identificado como funduscopy en una fuente clínica; no confundir con toma de fotografía retiniana sin examen.',
 'UF0527':'Uso explícito de health care access en comunicación institucional ACC; conservar acceso a atención y no convertirlo en utilización o cobertura efectiva.',
 'UF0529':'La fuente OMS sobre cloruro desarrolla la sal de potasio KCl. Se rechazó el falso positivo KCL en una dirección de correo de King’s College London.',
 'UF0540':'La fuente atesta el desenlace con calificativo non-fatal; no eliminar la negación ni confundir con mortalidad cardiovascular.',
 'UF0541':'El desenlace aparece dentro de fatal or non-fatal stroke; conservar la alternativa completa en la oración. La grafía no permite borrar fatal ni or.',
 'UF0546':'La fuente desarrolla intention to treat e ITT analysis; no equiparar con análisis por protocolo o imputación de datos.',
 'UF0548':'Atestación de double-masked en título de un ensayo. Exigir que el protocolo indique quién estaba enmascarado; la cadena no identifica por sí sola a los dos grupos.',
 'UF0550':'El suplemento ACC define COR. Se descarta Cor Vitae por ser una denominación ajena a class of recommendation.',
 'UF0551':'Herramienta oficial de ACC desarrolla LOE; no equiparar con clase de recomendación ni certeza GRADE.',
 'UF0556':'La fuente define RRR como reducción relativa del riesgo. No sustituir por reducción absoluta ni importar cifras del ejemplo.',
 'UF0557':'Atestación literal en un artículo sobre la guía de síndromes coronarios de 2025. La frase sola no identifica la guía de hipertensión. Proponer añadir explícitamente hypertension a cualquier referencia de investigación; la forma sin tema queda bloqueada como alias inequívoco.',
 'UF0558':'El título de una publicación indexada en PubMed usa el nombre PREVENT risk equations; la página AHA aporta contexto del modelo. Conservar horizonte temporal, población y desenlaces; no intercambiar con PCE o SCORE2.',
 'UF0562':'La frase se usa para riesgo cardiovascular a diez años en un estudio; conservar enfermedad cardiovascular general, horizonte y ecuación, sin añadir aterosclerosis.',
}
MISSING={
 'UF0015':'retire_unattested_ambiguous_alias',
 'UF0048':'retain_canonical_only_pending_literal_variant',
 'UF0080':'retain_canonical_only_pending_literal_variant',
 'UF0284':'retain_context_only_pending_literal_variant',
 'UF0320':'retain_canonical_only_pending_literal_variant',
 'UF0378':'retain_canonical_only_pending_literal_variant',
 'UF0385':'retain_context_only_pending_literal_variant',
 'UF0414':'retain_canonical_only_pending_literal_variant',
 'UF0465':'retain_context_only_pending_literal_variant',
 'UF0466':'retain_context_only_pending_literal_variant',
}
LIMITED={'UF0277','UF0286','UF0375'}
REJECTED={'UF0117','UF0336','UF0471'}

def main():
 assert sha(P/'surface_verification_124_discovery.json')==APPROVED_DISCOVERY_SHA,'New discovery requires a fresh editorial review; do not auto-accept new matches.'
 now=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds');inputs=read('surface_verification_124_targets.json');dis=read('surface_verification_124_discovery.json');canonical={c['id']:c for c in read('hypertension_research_en_es.json')['concepts']}
 assert len(dis['records'])==124 and len(SELECTIONS)+len(MISSING)==124
 assert set(SELECTIONS).isdisjoint(MISSING) and set(SELECTIONS)|set(MISSING)=={r['form_id'] for r in dis['records']}
 records=[];source_map={};sources=[]
 for r in dis['records']:
  fid=r['form_id'];c=canonical[r['concept_id']];evidence=None
  if fid in SELECTIONS:
   candidates=[b for b in r['candidates'] if SELECTIONS[fid] in b['url']]
   assert candidates,(fid,SELECTIONS[fid])
   # Prefer a directly opened passage over a search extract for the same URL.
   candidates.sort(key=lambda b:(0 if fid=='UF0424' and 'search57.' in b['cache_file'] else 1,0 if 'open' in b['cache_file'] else 1,b['cache_file']))
   chosen=candidates[0];raw=(P/chosen['cache_file']).read_text(encoding='utf-8');block=raw.split('--------------------------------------------------------------------------------')[chosen['block_index']-1].strip()
   assert sha(P/chosen['cache_file'])==chosen['cache_sha256'] and hashlib.sha256(block.encode('utf-8')).hexdigest()==chosen['block_sha256']
   assert ' '+norm(r['form'])+' ' in ' '+norm(block)+' '
   key=chosen['url']
   if key not in source_map:
    sid=f'SF{len(sources)+1:03}';source_map[key]=sid
    host=urlparse(key).hostname or ''
    priority=any(host==h or host.endswith('.'+h) for h in ['escardio.org','acc.org','heart.org','pubmed.ncbi.nlm.nih.gov','who.int','kdigo.org'])
    sources.append(dict(id=sid,url=key,title=chosen['title'],host=host,priority_domain=priority,consulted_on='2026-10-21',access_level='selected_direct_web_passage' if 'open' in chosen['cache_file'] else 'indexed_selected_passage_or_abstract',local_cache_file=chosen['cache_file'],cache_sha256=chosen['cache_sha256'],result_block_index=chosen['block_index'],result_block_sha256=chosen['block_sha256'],full_article_read_claimed=False))
   sid=source_map[key]
   kind='normalized_literal_in_reviewed_context';outcome='literal_verified_in_concept_context'
   if fid in LIMITED:kind='limited_source_use_not_accepted_as_primary_verification';outcome='limited_evidence_not_accepted'
   if fid in REJECTED:kind='literal_expression_but_not_strict_equivalence';outcome='unsafe_equivalence_reconfirmed'
   if fid in {'UF0557','UF0424'}:kind='literal_competing_guideline_or_diagnostic_reference';outcome='ambiguous_reference_restricted'
   language_basis='reviewed_english_passage' if r['language']=='en' else 'reviewed_spanish_passage'
   if fid in {'UF0044','UF0427','UF0498'}:language_basis='explicit_spanish_original_title_in_pubmed'
   if fid=='UF0497':language_basis='explicit_spanish_title_and_bilingual_author_keywords_in_pubmed'
   if fid=='UF0396':language_basis='explicit_bilingual_author_keywords_in_pubmed'
   if fid=='UF0493':language_basis='explicit_spanish_other_abstract_in_pubmed_index'
   if fid=='UF0461':language_basis='explicit_spanish_resumen_on_publisher_page'
   if fid=='UF0309':language_basis='language_independent_unit_symbol_attested_in_english'
   if fid in {'UF0315'}:language_basis='reviewed_spanish_section_in_bilingual_institutional_document'
   evidence=dict(source_id=sid,url=key,form=r['form'],language_basis=language_basis,locator_kind='tool_result_block_one_based',result_block_index=chosen['block_index'],local_cache_file=chosen['cache_file'],cache_sha256=chosen['cache_sha256'],result_block_sha256=chosen['block_sha256'],assessment=kind,literal_location_found=True,standalone_synonym_approval=False)
   if fid=='UF0424' and (P/'source_cache/surface124_pry_cardiovascular2013.selected_pages.json').exists():
    pdf=read('source_cache/surface124_pry_cardiovascular2013.selected_pages.json')
    pdf_file=P/'source_cache/surface124_pry_cardiovascular2013.pdf'
    assert sha(pdf_file)==pdf['source_pdf_sha256']
    page=next((pg for pg in pdf['selected_pages'] if 'prueba de captopril' in norm(pg['text']) and 'renovascular' in norm(pg['text'])),None)
    if page:
     assert hashlib.sha256(page['text'].encode('utf-8')).hexdigest()==page['sha256']
     evidence['supplementary_pdf_page']=dict(source_copy_sha256=pdf['source_pdf_sha256'],pdf_page_one_based=page['pdf_page'],extracted_page_sha256=page['sha256'],local_pdf='source_cache/surface124_pry_cardiovascular2013.pdf',local_selected_pages='source_cache/surface124_pry_cardiovascular2013.selected_pages.json',scope='Table 13 renovascular row reviewed; full-PDF availability does not mean complete manual reading.')
    else:
     evidence['supplementary_pdf_access']=dict(source_copy_sha256=pdf['source_pdf_sha256'],pdf_page_count=pdf['page_count'],local_pdf='source_cache/surface124_pry_cardiovascular2013.pdf',qualifying_text_page_not_extracted=True,used_as_attestation=False,scope='PDF downloaded but the selected definition remains supported by the explicit indexed Table 13 passage, not by an invented PDF locator.')
   if fid=='UF0277':evidence['access_caveat']='PMC publication is a clinical commentary about a meta-analysis; repository presence is not primary-study status.'
   if fid=='UF0286':evidence['access_caveat']='Institutional thesis table; not a selected peer-reviewed primary clinical publication.'
   if fid=='UF0375':evidence['access_caveat']='Professional secondary Spanish summary/translation; primary literal verification remains pending.'
  else:outcome='no_acceptable_literal_attestation'
  note=NOTES.get(fid,'Forma literal revisada en el contexto del concepto. Conservar calificadores, idioma, categoría gramatical y restricciones de la auditoría previa; esta atestación no autoriza sustitución automática.')
  if fid in MISSING and fid not in NOTES:note='La búsqueda prioritaria y complementaria no aportó una atestación literal aceptable para esta grafía exacta. Mantener la preferencia española/canónica ya cotejada y la restricción de contexto; no presentar la variante como literalmente verificada.'
  action=MISSING.get(fid,'retain_for_research_with_prior_context_restrictions')
  if fid in REJECTED:action='exclude_from_strict_alias_set_keep_related_expression_or_other_sense'
  if fid in LIMITED:action='hold_primary_literal_verification_do_not_promote'
  if fid=='UF0557':action='require_hypertension_topic_in_reference_do_not_expand_bare_alias'
  if fid=='UF0424':action='require_diagnostic_purpose_and_protocol_do_not_assume_aldosteronism_test'
  prior_restriction=r['status']
  records.append(dict(form_id=fid,concept_id=r['concept_id'],canonical_en=r['canonical_en'],preferred_es=c['preferred_es'],language=r['language'],form=r['form'],occurrence_ids=r['occurrence_ids'],previous_alias_safety_status=prior_restriction,decision=outcome,research_action=action,editorial_note=note,attestation=evidence,canonical_context_evidence=dict(file='bilingual_verification.json',record_id=r['concept_id'],scope='Previously crosschecked canonical pair only; does not establish literal attestation of this alternative.'),automatic_substitution_approved=False,independent_clinician_review='not_performed',reviewed_by='assistant',reviewed_at_utc=now))
 counts=dict(targets_reviewed=124,by_decision=dict(Counter(r['decision'] for r in records)),sources_selected=len(sources),priority_domain_sources=sum(s['priority_domain'] for s in sources),literal_locations_recorded=sum(r['attestation'] is not None for r in records),accepted_literal_in_concept_context=sum(r['decision']=='literal_verified_in_concept_context' for r in records),literal_verification_still_not_accepted=sum(r['decision'] in {'no_acceptable_literal_attestation','limited_evidence_not_accepted'} for r in records),automatic_substitution_approvals=0,pending_editorial_decisions=0)
 save('surface_verification_124_sources.json',dict(policy='Source supplement for this continuation only. SF IDs do not replace prior S/AS catalogs. Priority domains were searched first. Repository hosting is distinguished from authorship and indexed extracts from full-text reading.',sources=sources))
 save('surface_verification_124.json',dict(schema_version='1.0',reviewed_at_utc=now,input_targets_sha256=sha(P/'surface_verification_124_targets.json'),baseline_alias_review_sha256=inputs['baseline_alias_review_sha256'],input_discovery_sha256=sha(P/'surface_verification_124_discovery.json'),policy='Individual assistant editorial review of previously missing surface forms. Literal occurrence, concept correspondence, source quality, language and safe alias use are separate decisions. No automatic substitutions.',counts=counts,records=records))
 print(json.dumps(counts,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

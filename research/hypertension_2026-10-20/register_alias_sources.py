"""Record specifically consulted evidence without changing the canonical source catalog."""
import json,hashlib
from pathlib import Path
P=Path(__file__).resolve().parent
SOURCES=[
 ('AS01','AHA: diagnóstico vascular por MRA','https://www.heart.org/en/health-topics/peripheral-artery-disease/diagnosing-pad','alias_open1','official_page_selected_passage','Magnetic resonance angiography (MRA)','Lista de pruebas diagnósticas, línea web 30; revisión visible 2026-04-24.'),
 ('AS02','ACC: enfermedad arterial periférica','https://www.acc.org/about-acc/press-releases/2024/05/21/16/00/early-diagnosis-treatment-of-peripheral-artery-disease-essential-to-improve-outcomes-reduce-amputation-risk','alias_open1','official_page_selected_passage','peripheral artery disease (PAD)','Primer párrafo de la comunicación; líneas web 156–158.'),
 ('AS03','CARDia: diseño del ensayo de revascularización','https://pubmed.ncbi.nlm.nih.gov/15660030/','alias_search1','pubmed_indexed_title_and_abstract','Coronary Artery Revascularisation in Diabetes (CARDia)','Título y objetivo del resumen indexado; no corresponde a la cohorte CARDIA.'),
 ('AS04','KDIGO 2012: extensión variable de thiazide-type','https://kdigo.org/wp-content/uploads/2016/10/KDIGO-2012-Blood-Pressure-Guideline-English.pdf','alias_kdigo_location','official_pdf_selected_passage','thiazide-type diuretics','Página PDF 25 (índice web P24), capítulo 2; líneas 1668–1673. Uso histórico para terminología, no para recomendaciones actuales.'),
 ('AS05','AHA: PAC en arritmias','https://newsroom.heart.org/news/air-pollution-may-spur-irregular-heart-rhythms-in-healthy-teens','alias_search2','indexed_official_passage','premature atrial contractions (PAC)','Extracto indexado del comunicado AHA; no lectura completa de un artículo primario.'),
 ('AS06','PRA en trasplante renal','https://pubmed.ncbi.nlm.nih.gov/8000853/','alias_search2','pubmed_indexed_title_and_abstract','panel reactive antibodies (PRA)','Resumen PubMed indexado; no texto completo.'),
 ('AS07','AHA: ACS como síndrome coronario','https://www.heart.org/en/health-topics/heart-attack/about-heart-attacks/acute-coronary-syndrome','alias_search3','indexed_official_passage','acute coronary syndrome (ACS)','Quick Facts y cuerpo de página indexado; definición competidora de la endocrina.'),
 ('AS08','FMD como prueba endotelial','https://pubmed.ncbi.nlm.nih.gov/20952670/','alias_search4','pubmed_indexed_abstract','flow-mediated dilation (FMD)','Resumen indexado; no texto completo.'),
 ('AS09','IAH como hipertensión intraabdominal','https://pubmed.ncbi.nlm.nih.gov/18446319/','alias_search4','pubmed_indexed_abstract','intra-abdominal hypertension (IAH)','Objetivo del resumen indexado; no texto completo.'),
 ('AS10','PEG como procedimiento digestivo','https://pubmed.ncbi.nlm.nih.gov/8977937/','alias_search4','pubmed_indexed_abstract','Percutaneous endoscopic gastrostomy (PEG)','Resumen indexado; no texto completo.'),
 ('AS11','ARR como reducción absoluta del riesgo','https://pubmed.ncbi.nlm.nih.gov/24686884/','alias_search5','pubmed_indexed_abstract','Absolute Risk Reduction (ARR)','Objetivo del resumen indexado; no texto completo.'),
 ('AS12','CI como índice cardíaco','https://pubmed.ncbi.nlm.nih.gov/30540751/','alias_search5','pubmed_indexed_abstract','Cardiac index (CI)','Resumen indexado del estudio CITE; no texto completo.'),
 ('AS13','RR como frecuencia respiratoria','https://pubmed.ncbi.nlm.nih.gov/31251168/','alias_search5','pubmed_indexed_abstract','Respiratory rate (RR)','Resumen indexado; no texto completo.'),
 ('AS14','Uso contextual de clinical inertia','https://pubmed.ncbi.nlm.nih.gov/21301689/','alias_search3','pubmed_indexed_abstract','Clinical inertia','Discusión del resumen: uso intercambiable en este contexto; no prueba de identidad en toda taxonomía.'),
 ('AS15','RAS como estenosis de arteria renal','https://pubmed.ncbi.nlm.nih.gov/21722784/','alias_search6','pubmed_indexed_abstract','Renal artery stenosis (RAS)','Resumen indexado; no texto completo.'),
 ('AS16','Cochrane: RAR en español','https://www.cochrane.org/es/evidence/CD003610_benefits-and-harms-antibiotics-secondary-prevention-coronary-heart-disease','alias_search7','indexed_primary_systematic_review_spanish_summary','reducción absoluta del riesgo (RAR)','Obtención y análisis de datos del resumen de revisión. Fuente complementaria fuera de los dominios prioritarios para expansión española explícita.'),
 ('AS17','PAC y PRA en hipertensión','https://pubmed.ncbi.nlm.nih.gov/42162197/','alias_search8','pubmed_indexed_abstract','plasma aldosterone concentration (PAC)','Resumen indexado; no texto completo. Fuente explícita de expansión, distinta de una coincidencia de PAC en nombres o bibliografía.'),
 ('AS18','HRV: definición de variabilidad cardíaca','https://pubmed.ncbi.nlm.nih.gov/29034226/','alias_search8','pubmed_indexed_abstract','Heart rate variability (HRV)','Resumen indexado; no texto completo.'),
 ('AS19','FMD como enfermedad arterial','https://pubmed.ncbi.nlm.nih.gov/30648921/','alias_search9','pubmed_indexed_abstract','fibromuscular dysplasia (FMD)','Resumen indexado del consenso internacional; no texto completo.'),
 ('AS20','RR como medida de riesgo','https://pubmed.ncbi.nlm.nih.gov/38620441/','alias_search5','pubmed_indexed_abstract','relative risk (RR)','Resumen indexado; solo se usa para la expansión terminológica, sin adoptar otros detalles.'),
]
def main():
 records=[]
 for sid,title,url,snapshot,level,form,locator in SOURCES:
  f=P/f'source_cache/{snapshot}.web.txt';txt=f.read_text(encoding='utf-8')
  # Check the specific result block, not a term borrowed from another search hit.
  blocks=txt.split('--------------------------------------------------------------------------------')
  block=next((b for b in blocks if url in b and form.casefold() in b.casefold()),None)
  assert block is not None,(sid,url,form)
  records.append(dict(id=sid,title=title,url=url,consulted_on='2026-10-21',language='es' if sid=='AS16' else 'en',access_level=level,attested_short_expression=form,locator=locator,local_snapshot=str(f.relative_to(P)).replace('\\','/'),snapshot_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),result_block_sha256=hashlib.sha256(block.encode('utf-8')).hexdigest(),automatic_substitution_approved=False))
 (P/'alias_source_catalog.json').write_text(json.dumps(dict(policy='Supplement to sources.json for this alias audit. Public sources were prioritized; index/abstract-only access is explicit. Snapshots are local source evidence and excluded from the ZIP.',sources=records),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Registered',len(records),'specific source blocks')
if __name__=='__main__':main()

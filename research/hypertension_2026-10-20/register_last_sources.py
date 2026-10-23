import json
from pathlib import Path
p=Path(__file__).resolve().parent
s=json.loads((p/'sources.json').read_text(encoding='utf-8'))
items=[('S122','The Molecular Genetics of Gordon Syndrome','https://pubmed.ncbi.nlm.nih.gov/31795491/','2019'),('S123','Renal lithium clearance in the different stages of hypertension','https://pubmed.ncbi.nlm.nih.gov/1663969/','1991'),('S124','Fine particulate matter air pollution and blood pressure: the modifying role of psychosocial stress','https://pubmed.ncbi.nlm.nih.gov/24968081/','2014')]
items += [('S125','Practice guidelines for the emergency treatment of thrombotic microangiopathy','https://pubmed.ncbi.nlm.nih.gov/29534844/','2018'),('S126','Executive functions in patients with obstructive sleep apnea: exploring the prefrontal model','https://pubmed.ncbi.nlm.nih.gov/38349318/','2024'),('S127','Posterior reversible encephalopathy syndrome after neurosurgery: A literature review','https://pubmed.ncbi.nlm.nih.gov/25866131/','2015'),('S128','Neutropenia and hypotension during treatment with recombinant human erythropoietin','https://pubmed.ncbi.nlm.nih.gov/2396173/','1990')]
items += [('S129','Silent cerebral infarcts in basal ganglia are advanced in congenital protein C-deficient heterozygotes with hypertension','https://pubmed.ncbi.nlm.nih.gov/11497200/','2001'),('S130','Delphi panel study of current hypertension treatment patterns','https://pubmed.ncbi.nlm.nih.gov/11219475/','2001')]
for id,title,url,date in items:
 if id not in {x['id'] for x in s}: s.append(dict(id=id,title=title,url=url,organization='NLM PubMed / primary publication',language='en',publication_date=date,consulted_on='2026-10-20',access_level='abstract_or_indexed_abstract',notes='Terminology attestation, not a current clinical recommendation. Full article not claimed.'))
for x in s:
 if x['id'] in ['S125','S126','S127','S128']:
  x['language']='en,es'; x['access_level']='indexed_bibliographic_record'; x['notes']='Spanish original title, Spanish abstract or explicitly bilingual author keywords in indexed PubMed record. English abstract is not treated as Spanish text.'
 if x['id']=='S93': x['publication_date']='2015-04'; x['notes']='Sociedad Latinoamericana de Hipertensión regional program, edited by Jesús Antonio López Rivera, April 2015, ISBN 978-980-12-8207-5. Historical terminology only.'
(p/'sources.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
# An inaccessible browser challenge must not take precedence over a genuine indexed abstract.
for id in ['S122','S124']:
 q=p/'source_cache'/f'{id}.web.txt'
 if q.exists() and 'Total lines: 3' in q.read_text(encoding='utf-8'): q.rename(q.with_suffix('.blocked.txt'))

"""Freeze the completed canonical research and inventory every lexical occurrence."""
import json, hashlib, shutil, unicodedata, re
from pathlib import Path
from collections import defaultdict, Counter
P=Path(__file__).resolve().parent
def read(n): return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v): (P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def tokens(s):
 s=''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c))
 return ' '.join(re.findall(r"[^\W_]+(?:[’'][^\W_]+)*",s))
def main():
 checkpoint=P/'checkpoints/session3_657_verified'
 if not checkpoint.exists():
  checkpoint.mkdir()
  for p in P.iterdir():
   if p.is_file() and p.suffix in {'.json','.md','.txt','.zip'}:shutil.copy2(p,checkpoint/p.name)
 data=read('hypertension_research_en_es.json'); occurrences=[];targets=[]
 for index,c in enumerate(data['concepts'],1):
  def add(form,lang,role,path,expansion=None):
   item=dict(occurrence_id=f'AF{len(occurrences)+1:04}',concept_id=c['id'],concept_index=index,canonical_en=c['canonical_en'],form=form,language=lang,role=role,json_path=path,normalized=tokens(form))
   if expansion:item['declared_expansion']=expansion
   occurrences.append(item)
  for key,lang in [('aliases_en','en'),('variants_es','es')]:
   for i,f in enumerate(c[key]):add(f,lang,key,f'{key}[{i}]')
  for i,a in enumerate(c['abbreviations']):add(a['form'],a['language'],'abbreviation',f'abbreviations[{i}]',a['expansion'])
  for i,e in enumerate(c['original_entries']):
   for key in ['aliases','variants']:
    for j,f in enumerate(e.get(key,[])):add(f,'en','inherited_'+key,f'original_entries[{i}].{key}[{j}]')
  for i,f in enumerate(c['grouped_lexical_forms']):
   if f!=c['canonical_en']:add(f,'en','grouped_lexical_form',f'grouped_lexical_forms[{i}]')
  targets.extend([dict(concept_id=c['id'],form=c['canonical_en'],language='en',role='canonical_en'),dict(concept_id=c['id'],form=c['preferred_es'],language='es',role='preferred_es')])
 groups=defaultdict(list)
 for f in occurrences+targets:groups[tokens(f['form'])].append(f)
 collisions=[]
 for key,items in groups.items():
  if len({f['concept_id'] for f in items})>1:
   collisions.append(dict(normalized_form=key,concept_ids=sorted({f['concept_id'] for f in items}),members=items))
 save('alias_inventory.json',dict(schema_version='1.0',input_dataset_sha256=sha(checkpoint/'hypertension_research_en_es.json'),counts=dict(concepts=len(data['concepts']),occurrences=len(occurrences),roles=dict(Counter(f['role'] for f in occurrences)),unique_concept_language_form=len({(f['concept_id'],f['language'],f['form']) for f in occurrences}),normalized_cross_concept_collision_groups=len(collisions)),occurrences=occurrences,canonical_collision_targets=targets,collisions=collisions))
 lines=[]
 for i,c in enumerate(data['concepts'],1):
  fs=[f for f in occurrences if f['concept_id']==c['id']]
  lines.append(f"{i}|{c['canonical_en']}|{c['preferred_es']}|"+'; '.join(f"{f['occurrence_id']}:{f['role']}:{f['form']}" for f in fs))
 (P/'alias_inventory_review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps(read('alias_inventory.json')['counts'],ensure_ascii=False))
 print(json.dumps(collisions,ensure_ascii=False,indent=2))
if __name__=='__main__':main()

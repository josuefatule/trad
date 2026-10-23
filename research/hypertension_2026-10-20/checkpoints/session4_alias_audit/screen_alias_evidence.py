"""Lexical evidence and collision discovery only; never approves equivalence."""
import json, hashlib, sys, re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from verify_bilingual import norm
from prepare_alias_audit import tokens
P=Path(__file__).resolve().parent
def read(n):return json.loads((P/n).read_text(encoding='utf-8'))
def save(n,v):(P/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 inv=read('alias_inventory.json');data=read('hypertension_research_en_es.json');cm={c['id']:c for c in data['concepts']}
 corpus=read('source_cache/corpus.json');sm={s['source_id']:s for s in corpus}
 pages={s['source_id']:[' '+norm(t)+' ' for t in s['pages']] for s in corpus}
 grouped=defaultdict(list)
 for f in inv['occurrences']:grouped[(f['concept_id'],f['language'],f['form'])].append(f)
 records=[]
 for key,items in grouped.items():
  cid,lang,form=key;c=cm[cid];priority=list(dict.fromkeys(c['review']['translation_crosscheck_source_ids']+['S71','S29','S05','S10','S76','S98','S100','S89']+list(sm)))
  hit=None;needle=' '+norm(form)+' '
  for sid in priority:
   if sid not in sm:continue
   s=sm[sid]
   if lang not in s['language'].split(','):continue
   for i,page in enumerate(pages[sid]):
    if sid=='S29' and lang=='es' and i>=91:continue
    if needle in page:
     hit=dict(source_id=sid,url=s['url'],locator_kind=s['locator_kind'],locator_index=i+1,source_copy_sha256=s['sha256'],extracted_locator_sha256=hashlib.sha256(s['pages'][i].encode('utf-8')).hexdigest(),lexical_location_only=True,semantic_equivalence_verified_by_match=False)
     break
   if hit:break
  records.append(dict(form_id=f'UF{len(records)+1:04}',concept_id=cid,canonical_en=c['canonical_en'],language=lang,form=form,occurrence_ids=[i['occurrence_id'] for i in items],roles=sorted({i['role'] for i in items}),literal_location=hit))
 # Broad all-pairs character screening, only within language, with no runtime execution.
 entries={}
 for f in inv['occurrences']+inv['canonical_collision_targets']:
  k=(f['concept_id'],f['language'],tokens(f['form']))
  entries.setdefault(k,f)
 bylang=defaultdict(list)
 for (cid,lang,t),f in entries.items():
  if len(t)>=8:bylang[lang].append((cid,t,f['form']))
 pairs=[]
 for lang,forms in bylang.items():
  for i,(cid,a,rawa) in enumerate(forms):
   for did,b,rawb in forms[i+1:]:
    if cid==did or 2*min(len(a),len(b))/(len(a)+len(b))<.9:continue
    if SequenceMatcher(None,a,b).quick_ratio()<.9:continue
    ratio=SequenceMatcher(None,a,b).ratio()
    if ratio>=.90:pairs.append(dict(language=lang,concept_a=cid,form_a=rawa,concept_b=did,form_b=rawb,character_ratio=round(ratio,6),interpretation='screen_only_not_equivalence_or_observed_runtime_replacement'))
 save('alias_evidence_discovery.json',dict(policy='Literal locations and character similarities are search aids, not acceptance decisions.',records=records,near_form_screen=pairs))
 print('unique',len(records),'literal hits',sum(bool(r['literal_location']) for r in records),'no literal location',sum(not r['literal_location'] for r in records),'similarity screening pairs',len(pairs))
 for r in records:
  if not r['literal_location']:print(r['form_id'],r['canonical_en'],'|',r['language'],r['form'])
if __name__=='__main__':main()

"""Discover candidate attestations for the final 57; no approval or runtime edits."""
import json
from pathlib import Path
from verify_bilingual import norm,variants,find_corpus
P=Path(__file__).resolve().parent
def find3(forms,corpus,lang):
 from verify_bilingual import find
 for s in corpus:
  if s['language']!=lang and not (s['locator_kind']=='indexed_bilingual_author_keywords' and lang in s['language'].split(',')): continue
  h=find(forms,s['normalized_pages'])
  if h:
   h.update(source_id=s['source_id'],locator_kind=s['locator_kind'],url=s['url'],locator_index=h.pop('page_pdf'))
   return h
 return None
def main():
 data=json.loads((P/'checkpoints/session2_600_verified/hypertension_research_en_es.json').read_text(encoding='utf-8'))
 corpus=json.loads((P/'source_cache/corpus.json').read_text(encoding='utf-8'))
 for s in corpus:s['normalized_pages']=list(map(norm,s['pages']))
 forms={}
 for line in (P/'session3_search_forms.txt').read_text(encoding='utf-8').splitlines():
  if not line or line.startswith('#'):continue
  key,en,es=line.split('|');forms[key]={'en':en.split(';') if en else [],'es':es.split(';') if es else []}
 hits=[]
 for c in data['concepts']:
  if c['review']['translation_status']=='crosschecked_in_en_and_es_sources':continue
  f=forms.get(c['canonical_en'],{'en':[],'es':[]})
  en=find3(variants([c['canonical_en']]+f['en'],'en'),corpus,'en')
  es=find3(variants(f['es']+[c['preferred_es']],'es'),corpus,'es')
  hits.append(dict(id=c['id'],en=c['canonical_en'],es=c['preferred_es'],category=c['category'],en_hit=en,es_hit=es))
 (P/'session3_discovery.json').write_text(json.dumps(hits,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('Pending inventory',len(hits),'Both',sum(bool(x['en_hit'] and x['es_hit']) for x in hits))
 for h in hits:
  print(('BOTH' if h['en_hit'] and h['es_hit'] else 'MISS')+' | '+h['en']+' | EN:'+str(h['en_hit'])+' | ES:'+str(h['es_hit']))
if __name__=='__main__':main()

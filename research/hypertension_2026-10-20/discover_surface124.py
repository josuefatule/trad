"""Find candidate literal source blocks, with no acceptance decisions."""
import json,re,hashlib
from pathlib import Path
from verify_bilingual import norm
P=Path(__file__).resolve().parent
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 targets=json.loads((P/'surface_verification_124_targets.json').read_text(encoding='utf-8'))['targets']
 blocks={};files=sorted(set((P/'source_cache').glob('surface124_*.web.txt'))|set((P/'source_cache').glob('alias_*.web.txt')))
 for f in files:
  raw=f.read_text(encoding='utf-8')
  for i,text in enumerate(raw.split('--------------------------------------------------------------------------------'),1):
   text=text.strip()
   first=text.splitlines()[0] if text else ''
   m=re.search(r'\((https?://[^\s]+)\)\s*$',first)
   if not m:continue
   url=m.group(1);key=(url,sha(text.encode('utf-8')))
   if key in blocks:continue
   blocks[key]=dict(url=url,title=first[:m.start()].strip(),cache_file=str(f.relative_to(P)).replace('\\','/'),cache_sha256=sha(f.read_bytes()),block_index=i,block_sha256=key[1],text=text,normalized=' '+norm(text)+' ')
 records=[];review=[]
 for t in targets:
  candidates=[]
  for b in blocks.values():
   if ' '+norm(t['form'])+' ' not in b['normalized']:continue
   # Snippet matching excludes the requested search query and unrelated results.
   n=norm(b['text']);ix=n.find(norm(t['form']));before=n[max(0,ix-100):ix];after=n[ix+len(norm(t['form'])):ix+len(norm(t['form']))+170]
   candidates.append({k:v for k,v in b.items() if k not in ['text','normalized']}|dict(form=t['form'],normalized_context_before=before,normalized_context_after=after,acceptance='not_reviewed'))
  candidates.sort(key=lambda b:(0 if 'surface124_' in b['cache_file'] else 1,b['url']))
  records.append(dict(**t,candidates=candidates))
  review.append(f"{t['form_id']}|{t['canonical_en']}|{t['language']}|{t['form']}|CANDIDATES:{len(candidates)}")
  for i,b in enumerate(candidates[:5],1):review.append(f"  {i}|{b['url']}|{b['cache_file']}#{b['block_index']}|{b['normalized_context_before']} <<{t['form']}>> {b['normalized_context_after']}")
 output=dict(policy='Discovery only. Search snippets, source-language validity, meaning and complete title/abstract must be reviewed before accepting a surface form.',target_count=124,with_literal_candidate=sum(bool(r['candidates']) for r in records),without_literal_candidate=sum(not r['candidates'] for r in records),records=records)
 (P/'surface_verification_124_discovery.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (P/'surface_verification_124_discovery_review.txt').write_text('\n'.join(review)+'\n',encoding='utf-8')
 print(output['with_literal_candidate'],'targets with search candidates;',output['without_literal_candidate'],'without')
if __name__=='__main__':main()

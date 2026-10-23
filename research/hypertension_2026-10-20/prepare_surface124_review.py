"""Rank candidate passages for manual reading. Never accepts a match."""
import json,re
from pathlib import Path
P=Path(__file__).resolve().parent
PRIORITY=['pubmed.ncbi.nlm.nih.gov','professional.heart.org','heart.org','acc.org','kdigo.org','who.int','paho.org','secardiologia.es','seen.es','scielo','medlineplus.gov','cochrane.org']
def score(c):
 url=c['url'];n=next((i for i,p in enumerate(PRIORITY) if p in url),99)
 # A new targeted passage is easier to review; ranking does not indicate quality.
 return (n,0 if 'surface124_' in c['cache_file'] else 1,c['url'])
def main():
 d=json.loads((P/'surface_verification_124_discovery.json').read_text(encoding='utf-8'));lines=[]
 for r in d['records']:
  cs=sorted(r['candidates'],key=score)
  lines.append(r['form_id']+'|'+r['canonical_en']+'|'+r['language']+'|'+r['form'])
  for c in cs[:2]:lines.append(c['url']+'|'+c['cache_file']+'#'+str(c['block_index'])+'|'+c['normalized_context_before'][-70:]+' <<FORM>> '+c['normalized_context_after'][:210])
 (P/'surface_verification_124_ranked_review.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print('Prepared',len(d['records']),'records for manual review')
if __name__=='__main__':main()

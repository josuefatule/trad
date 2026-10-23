import json,sys
from verify_bilingual import HERE,norm
corpus=json.loads((HERE/'source_cache/corpus.json').read_text(encoding='utf-8'))
ids=sys.argv[1].split(',')
for query in sys.argv[2:]:
    print('\nQUERY',query)
    found=0
    for source in corpus:
        if source['source_id'] not in ids: continue
        for i,page in enumerate(source['pages']):
            text=norm(page); pos=text.find(norm(query))
            if pos<0: continue
            print(source['source_id'],source['locator_kind'],i+1,text[max(0,pos-90):pos+len(query)+240])
            found+=1
            if found>=3: break
        if found>=3: break
    if not found: print('NO HIT')

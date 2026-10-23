"""Find attestations for editorial terminology review, never change the live glossary.

String matches are discovery evidence only. Approval requires a reviewed decision
in bilingual_decisions.json; this program must not approve its own search hits.
"""
import json, re, unicodedata, hashlib
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(n): return json.loads((HERE/n).read_text(encoding='utf-8'))
def save(n,v): (HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def norm(s):
    s=re.sub(r'(?<=\w)\s*[\-\u00ad]\s*\n\s*(?=\w)', '',s)
    s=unicodedata.normalize('NFKD',s).casefold()
    s=''.join(c for c in s if not unicodedata.combining(c))
    # Extraction often glues superscript citation digits to the preceding word.
    # This is token separation only; digits and clinical qualifiers are retained.
    s=re.sub(r'(?<=[a-z])(?=\d)', ' ',s)
    return re.sub(r'[^\w%]+',' ',s).strip()
def find(forms,pages):
    for form in forms:
        needle=norm(form)
        if not needle: continue
        for i,page in enumerate(pages):
            if ' '+needle+' ' in ' '+page+' ':
                return {'form':form,'page_pdf':i+1}
    return None
def find_corpus(forms,corpus,lang):
    for source in corpus:
        if source['language']!=lang: continue
        hit=find(forms,source['normalized_pages'])
        if hit:
            hit['source_id']=source['source_id']; hit['locator_kind']=source['locator_kind']; hit['url']=source['url']
            hit['locator_index']=hit.pop('page_pdf')
            return hit
    return None
def variants(forms,lang):
    out=[]
    for f in forms:
        out.extend([f, f+'s'])
        pairs=([('blood pressure','BP'),('Blood Pressure','BP'),('randomized','randomised'),('edema','oedema'),('ischemi','ischaemi'),('hemorrhag','haemorrhag'),('hypokalemia','hypokalaemia'),('hyperkalemia','hyperkalaemia'),('estrogen','oestrogen')]
               if lang=='en' else [('presión arterial','PA'),('presión arterial','la PA'),('metaanálisis','metanálisis'),('monitorización','monitorización de'),('en consultorio','en consulta'),('del consultorio','de la consulta'),('eventos','episodios'),('eventos','eventos'),('sobreagregada','sobreañadida'),('inducida','inducida')])
        for a,b in pairs:
            if a in f: out.extend([f.replace(a,b), f.replace(a,b)+'s'])
    # Apply combinations too: "blood pressure in consultorio" -> "PA en consulta".
    for a,b in pairs:
        out.extend([f.replace(a,b) for f in list(out) if a in f])
    return list(dict.fromkeys(out))
def main():
    data=load('hypertension_research_en_es.json')
    corpus=load('source_cache/corpus.json')
    for source in corpus: source['normalized_pages']=list(map(norm,source['pages']))
    overrides=load('bilingual_search_forms.json') if (HERE/'bilingual_search_forms.json').exists() else {}
    for line in (HERE/'bilingual_search_forms.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'): continue
        canonical,a,b=line.split('|')
        current=overrides.setdefault(canonical,{'en':[],'es':[]})
        current['en'].extend(a.split(';') if a else [])
        current['es'].extend(b.split(';') if b else [])
    hits=[]
    for c in data['concepts']:
        o=overrides.get(c['canonical_en'],{})
        a=find_corpus(variants(o.get('en',[])+[c['canonical_en']],'en'),corpus,'en')
        # Acronym alone and an untranslated English variant cannot verify a Spanish translation.
        es_forms=[v for v in c['variants_es'] if len(v)>6 and norm(v)!=norm(c['canonical_en'])]
        b=find_corpus(variants(o.get('es',[])+[c['preferred_es']]+es_forms,'es'),corpus,'es')
        hits.append({'id':c['id'],'en':c['canonical_en'],'es':c['preferred_es'],'category':c['category'],'en_hit':a,'es_hit':b})
    save('bilingual_discovery.json',hits)
    print('Both',sum(bool(x['en_hit'] and x['es_hit']) for x in hits),'English',sum(bool(x['en_hit']) for x in hits),'Spanish',sum(bool(x['es_hit']) for x in hits))
    for x in hits:
        print(('BOTH' if x['en_hit'] and x['es_hit'] else 'MISS')+' | '+x['en']+' | '+x['es']+' | '+str(x['en_hit'])+' | '+str(x['es_hit']))
if __name__=='__main__': main()

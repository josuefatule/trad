"""Extract public source copies into a local terminology search corpus."""
from html.parser import HTMLParser
import json, hashlib
from pathlib import Path
from pypdf import PdfReader
HERE=Path(__file__).resolve().parent
class Visible(HTMLParser):
    def __init__(self): super().__init__(); self.skip=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag in ('p','div','li','h1','h2','h3','h4','section','tr','br'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag in ('p','div','li','h1','h2','h3','h4','section','tr'): self.parts.append('\n')
    def handle_data(self,d):
        if not self.skip: self.parts.append(d)
corpus=[]
for source in json.loads((HERE/'sources.json').read_text(encoding='utf-8')):
    if source['id']=='S71': continue  # Insert the complete English guideline once below.
    path=HERE/'source_cache'/(source['id']+'.source')
    webpath=HERE/'source_cache'/(source['id']+'.web.txt')
    indexed=HERE/'source_cache'/(source['id']+'.indexed.txt')
    if webpath.exists(): path=webpath
    elif indexed.exists(): path=indexed
    if not path.exists(): continue
    b=path.read_bytes()
    try:
        if path.name.endswith('.indexed.txt'):
            text=b.decode('utf-8').split('--------------------------------------------------------------------------------')[0]
            assert source['url'] in text.splitlines()[0], (source['id'],'indexed result is a different document')
            lines=text.splitlines()
            pages=['\n'.join(lines[i:i+35]) for i in range(0,len(lines),35)]; kind='indexed_excerpt_block_35_lines'
        elif path.suffix=='.txt':
            import re
            fragments=[b.decode('utf-8')]+[p.read_text(encoding='utf-8') for p in sorted((HERE/'source_cache').glob(source['id']+'.part*.web.txt'))]
            rawlines='\n'.join(fragments)
            lines=[re.sub(r'^L\d+(?:@P[\d-]+)?:\s*','',line) for line in rawlines.splitlines() if re.match(r'^L\d+',line)]
            pages=['\n'.join(lines[i:i+35]) for i in range(0,len(lines),35)]; kind='web_text_block_35_lines'
        elif b.startswith(b'%PDF'):
            extracted=path.with_suffix('.extracted.json')
            if extracted.exists(): pages=json.loads(extracted.read_text(encoding='utf-8'))
            else:
                pages=[p.extract_text() for p in PdfReader(path).pages]
                extracted.write_text(json.dumps(pages,ensure_ascii=False),encoding='utf-8')
            kind='pdf_page'
        else:
            html=b.decode('utf-8',errors='replace'); parser=Visible(); parser.feed(html)
            text='\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
            pages=['\n'.join(text.splitlines()[i:i+35]) for i in range(0,len(text.splitlines()),35)]; kind='text_block_35_lines'
        record={'source_id':source['id'],'language':source['language'],'url':source['url'],'sha256':hashlib.sha256(b).hexdigest(),'locator_kind':kind,'pages':pages}
        if source['id'] in ['S159','S160','S161']:
            # Explicit bilingual author keywords, not English prose misclassified as Spanish.
            text='\n'.join(pages)
            start=text.find('## Keywords')
            if start>=0:
                segment=text[start:]; end=segment.find('\n## ',3)
                segment=segment[:end] if end>=0 else segment
            else:
                segment='\n'.join(line for line in text.splitlines() if 'Keywords:' in line)
            assert segment, (source['id'],'bilingual author keywords not retrieved')
            record.update(pages=[segment],language='en,es',locator_kind='indexed_bilingual_author_keywords',page_languages=['en,es'])
        if source['id'] in ['S105','S125','S126','S127','S128']:
            # The indexed PubMed response contains genuine English and Spanish abstracts.
            # Only its Spanish "Other abstract" segment is eligible as Spanish evidence.
            text='\n'.join(pages)
            if source['id']=='S125':
                lines=[line for line in text.splitlines() if line.startswith('Keywords:')]
                record['pages']=lines; record['language']='es'; record['locator_kind']='indexed_bilingual_author_keywords'
            elif source['id'] in ['S127','S128']:
                lines=[line for line in text.splitlines() if line.startswith('Original title:')]
                record['pages']=lines; record['language']='es'; record['locator_kind']='indexed_spanish_original_title'
            else:
                start=text.find('## Other abstract'); end=text.find('## MeSH',start)
                record['pages']=[text[start:end if end>=0 else None]] if start>=0 else []
                record['language']='es'; record['locator_kind']='indexed_other_abstract'
        corpus.append(record)
    except Exception as e: print(source['id'],str(e))
enpages=json.loads((HERE/'source_cache/esc2024_en.pages.json').read_text(encoding='utf-8'))
corpus.insert(0,{'source_id':'S71','language':'en','url':'https://repisalud.isciii.es/bitstreams/4fe1933e-3844-454d-9cef-4a64b5debafe/download','sha256':hashlib.sha256((HERE/'source_cache/esc2024_en.pdf').read_bytes()).hexdigest(),'locator_kind':'pdf_page','pages':enpages})
(HERE/'source_cache/corpus.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2),encoding='utf-8')
print('Extracted',len(corpus),'sources')

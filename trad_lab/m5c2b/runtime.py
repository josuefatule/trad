"""Real original DeepL adapter, explicit EN/ES, bounded private request trace."""
import json,os,re,time
from pathlib import Path
from urllib.parse import urlsplit
from app.translation.engine import TranslationStatus
from app.translation.providers import DeepLTranslatorProvider

BUDGET={'calls':0,'characters':0}

def read_local_config():
    result={}
    for line in Path('C:/live-captions/.env').read_text(encoding='utf-8-sig').splitlines():
        m=re.fullmatch(r'\s*(?:export\s+)?(DEEPL_API_KEY|DEEPL_AUTH_KEY|DEEPL_API_URL)\s*=\s*(.*?)\s*',line)
        if not m:continue
        name,value=m.groups()
        if value.startswith(('"',"'")):
            end=value.find(value[0],1)
            if end<0 or (value[end+1:].strip() and not value[end+1:].strip().startswith('#')):raise ValueError('Invalid local provider setting')
            value=value[1:end]
        else:value=re.split(r'\s+#',value,maxsplit=1)[0].rstrip()
        result[name]=value
    key=result.get('DEEPL_API_KEY') or result.get('DEEPL_AUTH_KEY')
    url=result.get('DEEPL_API_URL') or 'https://api-free.deepl.com/v2/translate'
    parsed=urlsplit(url)
    if not key:raise RuntimeError('Local DeepL credential unavailable')
    if parsed.scheme!='https' or parsed.hostname not in ('api-free.deepl.com','api.deepl.com') or parsed.path!='/v2/translate' or parsed.query or parsed.username or parsed.password:raise ValueError('Only official DeepL translate endpoint permitted')
    return {'key':key,'url':url}

def configure_environment():
    from trad_lab.m5b.runtime import configure_environment as base
    base()
    secret=read_local_config()
    os.environ.update(TRANSLATION_ENABLED='1',TRANSLATION_PROVIDER='deepl',TRANSLATION_SOURCE_LANGUAGE='en',TRANSLATION_TARGET_LANGUAGE='es',DEEPL_AUTH_KEY=secret['key'],DEEPL_API_URL=secret['url'])

class TracedProvider:
    name='deepl'
    def __init__(self,provider):self.provider=provider
    def record(self,data):
        p=Path(os.environ['CAPTIONS_LOG_DIR'])/'translation_trace.jsonl';p.parent.mkdir(parents=True,exist_ok=True)
        with p.open('a',encoding='utf-8') as f:f.write(json.dumps({'perf_counter_ns':time.perf_counter_ns(),**data},ensure_ascii=False)+'\n')
    async def translate(self,request):
        if (request.source_language,request.target_language)!=('en','es'):raise ValueError('EN to ES required')
        if BUDGET['calls']>=128 or BUDGET['characters']+len(request.normalized_text)>20000:raise ValueError('Experimental provider budget exhausted')
        BUDGET['calls']+=1;BUDGET['characters']+=len(request.normalized_text)
        self.record({'event':'request','request':request.to_dict(),'call':BUDGET['calls']})
        try:result=await self.provider.translate(request)
        except BaseException as exc:
            self.record({'event':'failure','session_id':request.session_id,'segment_id':request.segment_id,'sequence':request.sequence,'error_type':type(exc).__name__,'http_status':getattr(exc,'code',None)})
            raise
        self.record({'event':'response','session_id':request.session_id,'segment_id':request.segment_id,'sequence':request.sequence,'translated_text':result})
        return result

def provider_from_config(config):
    if not config.enabled or config.provider!='deepl' or not config.deepl_auth_key or (config.source_language,config.target_language)!=('en','es'):raise RuntimeError('B requires explicit real DeepL EN to ES')
    provider=DeepLTranslatorProvider(config.deepl_auth_key,config.deepl_api_url,min(config.timeout_seconds,config.request_deadline_seconds))
    return TracedProvider(provider),TranslationStatus('ready','deepl','Ensayo B; configured, first request verifies API')

def install(app):
    from trad_lab.m5c2.runtime import install as base
    base(app)
    import app.translation.engine as engine
    engine.provider_from_config=provider_from_config
    app.router.routes[:]=[r for r in app.router.routes if getattr(r,'path',None)!='/m5c/capabilities']
    @app.get('/m5c/capabilities')
    async def capabilities():
        return {'phase':'M5-C2-B','physical_enabled':True,'real_deepl_enabled':True,'translation_enabled':True,'direction':'en-es','resampler':'fir127-candidate','credit':'pcm_credit_v1','evidence':'owner_upload_v1','max_provider_calls':128,'max_provider_characters':20000}

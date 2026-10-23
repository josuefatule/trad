"""Build a new isolated copy; never edit the workspace app or any .env."""
import argparse
import json
from pathlib import Path
import shutil
from trad_lab.audio import digest

ROOT=Path('C:/live-captions')
BASELINE=ROOT/'logs/trad_lab/m5a_20261020T201327Z/gpu_r1/turbo'


def prepare(out):
    out=Path(out).resolve();allowed=(ROOT/'logs/trad_lab').resolve()
    if not out.is_relative_to(allowed) or out==allowed:raise ValueError('New private lab directory required')
    out.mkdir(parents=True,exist_ok=False);copy=out/'copy';copy.mkdir()
    original={}
    for folder in ('app','glossaries','trad_lab'):
        for source in (ROOT/folder).rglob('*'):
            if not source.is_file() or '__pycache__' in source.parts or source.suffix not in ('.py','.js','.cjs','.css','.html','.json','.md'):continue
            name=source.relative_to(ROOT).as_posix();original[name]=digest(source)
            target=copy/name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():raise FileExistsError('Concurrent destination modification')
            shutil.copyfile(source,target)
            if digest(target)!=original[name] or digest(source)!=original[name]:raise ValueError('Concurrent source changed during freeze: '+name)
    def patch(name,old,new):
        path=copy/name
        if digest(path)!=original[name]:raise ValueError('Concurrent copy modification: '+name)
        text=path.read_text(encoding='utf-8')
        if text.count(old)!=1:raise ValueError('Anchor changed: '+name)
        path.write_text(text.replace(old,new),encoding='utf-8',newline='\n')
    patch('app/main.py','load_project_env()','from trad_lab.m5b.runtime import configure_environment\nconfigure_environment()')
    # Two independent edits to this one newly owned copy, with an updated guard.
    original_main=digest(copy/'app/main.py')
    text=(copy/'app/main.py').read_text(encoding='utf-8')
    for old,new in [('from app.asr.whisperlivekit_client import relay','from trad_lab.m5b.runtime import experimental_relay as relay'),
                    ('    return app\n','    from trad_lab.m5b.runtime import install\n    install(app)\n    return app\n')]:
        if text.count(old)!=1:raise ValueError('Main hook anchor changed')
        text=text.replace(old,new)
    if digest(copy/'app/main.py')!=original_main:raise ValueError('Concurrent main-copy edit')
    (copy/'app/main.py').write_text(text,encoding='utf-8',newline='\n')
    relay_name='app/asr/whisperlivekit_client.py'
    relay_source=(copy/relay_name).read_text(encoding='utf-8')
    relay_patched=relay_source
    for old,new in [
        ('from websockets.asyncio.client import connect','from trad_lab.m5b.runtime import connect, relay_wait'),
        ('await asyncio.wait_for(upstream.send(audio),reliability.websocket_send_seconds)',
         "await relay_wait('upstream_send',upstream.send(audio),reliability.websocket_send_seconds)"),
        ('await asyncio.wait_for(receiver, settings.stop_timeout)',
         "await relay_wait('eof_drain',receiver,settings.stop_timeout)")]:
        if relay_patched.count(old)!=1:raise ValueError('Relay phase anchor changed')
        relay_patched=relay_patched.replace(old,new)
    patch(relay_name,relay_source,relay_patched)
    # Only the newly created main copy gets the phase-aware error classification.
    text=(copy/'app/main.py').read_text(encoding='utf-8')
    old='''run.fail("stop_timeout" if isinstance(exc,TimeoutError) else "resource_budget_exhausted"
                         if isinstance(exc,RuntimeError) and "budget" in str(exc).lower() else "session_transport_error")'''
    new='''run.fail(getattr(exc,"transport_code",None) or ("eof_drain_timeout" if isinstance(exc,TimeoutError) else "resource_budget_exhausted"
                         if isinstance(exc,RuntimeError) and "budget" in str(exc).lower() else "session_transport_error"))'''
    if text.count(old)!=1:raise ValueError('Error classification anchor changed')
    if (copy/'app/main.py').read_text(encoding='utf-8')!=text:raise ValueError('Concurrent main-copy edit')
    (copy/'app/main.py').write_text(text.replace(old,new),encoding='utf-8',newline='\n')
    patch('app/operator_control.py','    text = str(error).lower()',
          '''    if getattr(error,"transport_code",None):
        return error.transport_code, "Transporte experimental interrumpido; contenido incompleto. No reiniciar sin revisar el diagnóstico."
    text = str(error).lower()''')
    patch('app/static/operator_console.js',
          'session_transport_error:"Conexión de sesión perdida; sesión incompleta.",stop_timeout:',
          '''upstream_send_timeout:"Envío de audio interrumpido; sesión incompleta.",
        pcm_credit_wait_timeout:"El audio anterior no fue procesado y entregado dentro del plazo; sesión incompleta.",
        browser_delivery_timeout:"Entrega de resultados interrumpida; sesión incompleta.",
        eof_drain_timeout:"Final de audio recibido; no terminó la entrega de resultados.",
        unattributed_transport_timeout:"Plazo de transporte agotado; sesión incompleta. Revisar diagnóstico.",
        session_transport_error:"Conexión de sesión perdida; sesión incompleta.",stop_timeout:''')
    patch('app/static/operator.js','window.open("/capture",','window.open("/m5b/file-capture",')
    patch('app/templates/operator.html','</head>','<script src="/static/m5b_diagnostics.js"></script></head>')
    for source,name in [('diagnostics.js','app/static/m5b_diagnostics.js'),('file_capture.js','app/static/m5b_file_capture.js'),
                        ('file_capture.html','app/templates/m5b_file_capture.html')]:
        shutil.copyfile(ROOT/'trad_lab/m5b'/source,copy/name)
    inputs=[]
    for result in sorted(BASELINE.glob('*/result.json')):
        record=json.loads(result.read_text(encoding='utf-8'))
        inputs.append({'id':record['sample']['id'],'sha256':record['sample']['sha256'],
                       'pcm_sha256':record['received_pcm_sha256'],'path':record['sample']['path']})
    (copy/'app/static/m5b_inputs.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    manifest={p.relative_to(copy).as_posix():digest(p) for p in copy.rglob('*') if p.is_file()}
    plan={'copy':str(copy),'manifest':manifest,'source_originals':original,
          'backend_port':18000,'trad_port':18010,'deepl_enabled':False,'microphone_enabled':False,
          'backend_choices':['turbo','wlk'],'default_backend':None,'inputs':inputs,
          'profile':'M5-A unchanged: Turbo en, LA2/1s/2s, adaptive15/30, installed Silero defaults',
          'phase':'M5-B2','transport_flow':{'protocol':'pcm_credit_v1','pcm_frame_bytes':64000,
              'inflight_frames':1,'default_pacing':'realtime','credit_wait_seconds':37.,'file_credit_seconds':39.},
          'services_started':False,'human_authorization':'PENDING explicit later E2E authorization',
          'credentials_copied':False,'env_file_created':False}
    (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    return plan


def verify(plan):
    plan=Path(plan).resolve();data=json.loads(plan.read_text(encoding='utf-8'))
    copy=Path(data['copy']).resolve()
    if not copy.is_relative_to((ROOT/'logs/trad_lab').resolve()) or copy.name!='copy':raise ValueError('Invalid lab copy')
    if (data['backend_port'],data['trad_port'],data['deepl_enabled'],data['microphone_enabled'])!=(18000,18010,False,False):raise ValueError('Unsafe plan')
    if data.get('phase')=='M5-B2' and data.get('transport_flow')!={'protocol':'pcm_credit_v1','pcm_frame_bytes':64000,
            'inflight_frames':1,'default_pacing':'realtime','credit_wait_seconds':37.,'file_credit_seconds':39.}:
        raise ValueError('Experimental flow configuration changed')
    for name,sha in data['manifest'].items():
        target=(copy/name).resolve()
        if not target.is_relative_to(copy) or digest(target)!=sha:raise ValueError('Frozen copy changed: '+name)
    actual={p.relative_to(copy).as_posix() for p in copy.rglob('*') if p.is_file() and
            '__pycache__' not in p.parts and '.runtime' not in p.parts}
    if actual!=set(data['manifest']):raise ValueError('Unmanifested or missing files in frozen copy')
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    plan=prepare(args.out);print(json.dumps({'copy':plan['copy'],'files':len(plan['manifest']),'services_started':False}))

"""Explicit manual entry points, restricted to the frozen lab copy/ports.

These commands MUST NOT be run until the user authorizes M4-B services.
"""
import json
import os
from pathlib import Path
import socket
import sys


def listening(port):
    for host,family in [('127.0.0.1',socket.AF_INET),('::1',socket.AF_INET6)]:
        with socket.socket(family) as s:
            s.settimeout(.3)
            if s.connect_ex((host,port)) == 0: return True
    return False


def serve(role, plan, authorization):
    if authorization != 'M4-B aprobado hasta 3 sesiones': raise ValueError('Explicit human M4-B authorization required first')
    plan = Path(plan).resolve(); data = json.loads(plan.read_text(encoding='utf-8'))
    copy = Path(data['copy']).resolve()
    if not copy.is_relative_to(Path('C:/live-captions/logs/trad_lab').resolve()): raise ValueError('Invalid isolated copy')
    from .prepare import digest
    for name, expected in data['original_sources'].items():
        expected = data['modified_copy_only'].get(name,expected)
        if digest(copy/name) != expected: raise ValueError('Frozen copy changed: '+name)
    if listening(8000) or listening(8010): raise RuntimeError('Close LIVE services manually after STOP; never compete with them')
    port = 18000 if role == 'wlk' else 18010
    if listening(port): raise RuntimeError('Lab port already occupied; do not start a duplicate')
    if role == 'trad' and not listening(18000): raise RuntimeError('Start and verify the authorized WLK first')
    # Inherited credentials/config must not override the isolated .env.
    for key in list(os.environ):
        if key.startswith(('DEEPL_', 'TRANSLATION_', 'SEGMENT_', 'RELIABILITY_', 'CAPTIONS_', 'CAPTION_', 'OPERATOR_', 'NORMALIZER_')):
            os.environ.pop(key)
    os.environ.update(data['config'])
    os.environ.update(HF_HUB_OFFLINE='1', HF_DATASETS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    sys.path.insert(0,str(copy)); os.chdir(copy)
    # Prevent previously imported production app modules from being reused.
    if any(n == 'app' or n.startswith('app.') for n in sys.modules): raise RuntimeError('Use a fresh process')
    from .tap import WireTap
    if role == 'trad':
        from app.main import app
        import uvicorn
        uvicorn.run(WireTap(app, plan.parent/'trad_wire','/ws/session'),host='127.0.0.1',port=18010,log_level='warning')
    else:
        from trad_lab.safety import gpu_snapshot
        if int(gpu_snapshot()['free_mib']) < 2200: raise RuntimeError('Insufficient GPU reserve; no automatic profile change')
        decoder=Path('C:/Users/JF/.cache/whisper/small.pt')
        if not decoder.is_file() or digest(decoder)!='9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794':
            raise RuntimeError('Cached small missing/changed; no download allowed')
        from faster_whisper.utils import download_model
        download_model('small',local_files_only=True)
        os.environ['PATH'] = 'C:/live-captions/.venv-wlk/Lib/site-packages/torch/lib'+os.pathsep+os.environ['PATH']
        sys.argv = ['m4b-wlk','--backend','faster-whisper','--model','small','--lan','en',
                    '--pcm-input','--host','127.0.0.1','--port','18000']
        from whisperlivekit import basic_server
        basic_server.app.add_middleware(WireTap,root=plan.parent/'wlk_wire',path='/asr')
        from trad_lab.wlk_probe_server import main
        from .watchdog import Telemetry
        telemetry=Telemetry(plan.parent);telemetry.start()
        try:main()
        except BaseException as exc:
            (plan.parent/'wlk_exit.json').write_text(json.dumps({'reason':type(exc).__name__,
                'oom':'out of memory' in str(exc).lower(),'automatic_retry':False}),encoding='utf-8')
            raise
        finally:telemetry.close()

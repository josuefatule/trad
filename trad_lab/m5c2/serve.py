"""Authorized C2-A only. Never reads DeepL keys or switches provider."""
import argparse
import os
from pathlib import Path
from .prepare import verify

AUTH='M5-C2 A ASR físico autorizado'


def preflight_dependencies():
    """Check the lazy session imports before loading a model or listening."""
    from trad_lab.m5b.flow import CreditConnection, FlowTrace
    return CreditConnection, FlowTrace


def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['backend','trad']);p.add_argument('--plan',required=True);p.add_argument('--authorization',required=True);a=p.parse_args()
    if a.authorization!=AUTH:raise ValueError('C2-A authorization required')
    data=verify(a.plan);copy=Path(data['copy']).resolve();run=Path(a.plan).resolve().parent
    if Path.cwd().resolve()!=copy or Path(__file__).resolve().parents[2]!=copy:raise RuntimeError('Frozen copy required')
    from trad_lab.m4b.server import listening
    if any(listening(x) for x in (8000,8010)):raise RuntimeError('LIVE ports occupied')
    port=18000 if a.role=='backend' else 18010
    if listening(port):raise RuntimeError('Experimental port occupied')
    preflight_dependencies()
    for k in list(os.environ):
        if k.startswith(('DEEPL_','TRANSLATION_','CAPTION_','CAPTIONS_','SEGMENT_','NORMALIZER_','RELIABILITY_','OPERATOR_','WLK_')):os.environ.pop(k)
    os.environ.update(M5B_BACKEND='turbo',CAPTIONS_LOG_DIR=str(run/'operational_logs'),TRANSLATION_ENABLED='0',WLK_WS_URL='ws://127.0.0.1:18000/asr')
    key=copy/'.runtime/m5b-service-key.txt';os.environ['M5B_SERVICE_KEY_FILE']=str(key)
    if a.role=='backend':
        if key.exists():raise RuntimeError('Previous service runtime; no automatic retry')
        from trad_lab.m5b.serve import restrict_new_key
        restrict_new_key(key)
        from trad_lab.m5b.model import load_decoder
        from trad_lab.m5b.transport import Broker,TurboService
        app=TurboService(Broker(load_decoder(run/'turbo_runtime'),run/'turbo_wire'),key.read_text(encoding='utf-8').strip())
    else:
        if not key.is_file() or not listening(18000):raise RuntimeError('Experimental backend must be ready')
        from app.main import app
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=port,log_level='warning',access_log=False,ws_max_size=1048576,ws_max_queue=4)


if __name__=='__main__':main()

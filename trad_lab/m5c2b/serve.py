"""Real B capabilities only in a fresh frozen lab copy, existing .venv-wlk."""
import argparse,os
from pathlib import Path
from .prepare import verify
AUTH='M5-C2 B DeepL OBS autorizado'
def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['backend','trad']);p.add_argument('--plan',required=True);p.add_argument('--authorization',required=True);a=p.parse_args()
    if a.authorization!=AUTH:raise ValueError('B authorization required')
    d=verify(a.plan);copy=Path(d['copy']).resolve();run=Path(a.plan).resolve().parent
    if Path.cwd().resolve()!=copy or Path(__file__).resolve().parents[2]!=copy:raise RuntimeError('Frozen B copy required')
    from trad_lab.m4b.server import listening
    if any(listening(x) for x in (8000,8010)) or listening(18000 if a.role=='backend' else 18010):raise RuntimeError('Ports occupied')
    from trad_lab.m5c2.serve import preflight_dependencies
    preflight_dependencies()
    for k in list(os.environ):
        if k.startswith(('DEEPL_','TRANSLATION_','CAPTION_','CAPTIONS_','SEGMENT_','NORMALIZER_','RELIABILITY_','OPERATOR_','WLK_')):os.environ.pop(k)
    os.environ.update(M5B_BACKEND='turbo',CAPTIONS_LOG_DIR=str(run/'operational_logs'),WLK_WS_URL='ws://127.0.0.1:18000/asr')
    key=copy/'.runtime/m5b-service-key.txt';os.environ['M5B_SERVICE_KEY_FILE']=str(key)
    if a.role=='backend':
        if key.exists():raise RuntimeError('Existing runtime; no automatic retry')
        from trad_lab.m5b.serve import restrict_new_key
        restrict_new_key(key)
        from trad_lab.m5b.model import load_decoder
        from trad_lab.m5b.transport import Broker,TurboService
        app=TurboService(Broker(load_decoder(run/'turbo_runtime'),run/'turbo_wire'),key.read_text().strip())
    else:
        if not key.is_file() or not listening(18000):raise RuntimeError('Backend required')
        from app.main import app
    import uvicorn
    uvicorn.run(app,host='127.0.0.1',port=18000 if a.role=='backend' else 18010,log_level='warning',access_log=False,ws_max_size=1048576,ws_max_queue=4)
if __name__=='__main__':main()

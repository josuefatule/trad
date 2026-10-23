"""Prepared entry point. Do not execute before later explicit E2E approval."""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from .prepare import verify

AUTHORIZATION='M5-B E2E aislado autorizado'


def restrict_new_key(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:f.write(secrets.token_urlsafe(48))
    path.chmod(0o600)
    if os.name=='nt':
        account=os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
        result=subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',account+':(F)','*S-1-5-18:(F)'],capture_output=True)
        if result.returncode:raise RuntimeError('Cannot restrict new lab key; abort')


def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['backend','trad'])
    p.add_argument('--plan',required=True);p.add_argument('--backend',choices=['turbo','wlk'],required=True)
    p.add_argument('--authorization',required=True);args=p.parse_args()
    if args.authorization!=AUTHORIZATION:raise ValueError('Later explicit human E2E approval required')
    data=verify(args.plan);copy=Path(data['copy']).resolve();run=Path(args.plan).resolve().parent
    if Path(__file__).resolve().parents[2]!=copy or Path.cwd().resolve()!=copy:raise RuntimeError('Invoke the frozen module from its copy directory')
    from trad_lab.m4b.server import listening
    if any(listening(port) for port in (8000,8010)):raise RuntimeError('LIVE ports occupied; stop without touching LIVE')
    port=18000 if args.role=='backend' else 18010
    if listening(port):raise RuntimeError('Experimental port already occupied')
    for name in list(os.environ):
        if name.startswith(('DEEPL_','TRANSLATION_','CAPTIONS_','CAPTION_','SEGMENT_','NORMALIZER_','RELIABILITY_','OPERATOR_','WLK_')):os.environ.pop(name)
    os.environ.update(M5B_BACKEND=args.backend,CAPTIONS_LOG_DIR=str(run/'operational_logs'),TRANSLATION_ENABLED='0',
                      CAPTIONS_LANGUAGE='en',WLK_WS_URL='ws://127.0.0.1:18000/asr')
    key=copy/'.runtime/m5b-service-key.txt'
    os.environ['M5B_SERVICE_KEY_FILE']=str(key)
    if args.role=='trad':
        if not listening(18000):raise RuntimeError('Authorized experimental backend must be ready first')
        if args.backend=='turbo' and not key.is_file():raise RuntimeError('Missing private backend key')
        from app.main import app
        import uvicorn
        uvicorn.run(app,host='127.0.0.1',port=18010,log_level='warning',access_log=False,ws_max_size=1048576,ws_max_queue=4)
    elif args.backend=='turbo':
        # A fresh service key per process; old keys are preserved, never overwritten.
        if key.exists():raise RuntimeError('Prior service key exists; review closure and create a new prepared run')
        restrict_new_key(key)
        from .model import load_decoder
        from .transport import Broker,TurboService
        decoder=load_decoder(run/'turbo_runtime')
        service=TurboService(Broker(decoder,run/'turbo_wire'),key.read_text(encoding='utf-8').strip())
        import uvicorn
        uvicorn.run(service,host='127.0.0.1',port=18000,log_level='warning',access_log=False,ws_max_size=1048576,ws_max_queue=4)
    else:
        # Explicit rollback only. No fallback, model/profile substitution or download.
        from trad_lab.audio import digest
        snapshot=Path('C:/Users/JF/.cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots/536b0662742c02347bc0e980a01041f333bce120')
        if digest(snapshot/'model.bin')!='3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671':raise RuntimeError('Rollback small cache changed')
        pt=Path('C:/Users/JF/.cache/whisper/small.pt')
        if not pt.is_file() or digest(pt)!='9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794':raise RuntimeError('Rollback PyTorch small missing/changed; no download')
        os.environ.update(HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1')
        os.environ['PATH']='C:/live-captions/.venv-wlk/Lib/site-packages/torch/lib'+os.pathsep+os.environ['PATH']
        sys.argv=['m5b-wlk','--backend','faster-whisper','--model','small','--lan','en','--pcm-input','--host','127.0.0.1','--port','18000']
        from app.asr.wlk_server import main as wlk_main
        wlk_main()


if __name__=='__main__':main()

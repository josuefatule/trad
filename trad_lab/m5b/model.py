"""Only cached evaluated Turbo; loaded only by an explicitly invoked lab run."""
import json
import os
from pathlib import Path
import numpy as np
from trad_lab.audio import digest
from trad_lab.m4c.incremental import Word
from trad_lab.runner import DECODE,environment

OPTIONS={**DECODE,'vad_filter':True,'initial_prompt':None,'hotwords':None}
WORKSPACE=Path('C:/live-captions')


def load_decoder(evidence):
    from trad_lab.safety import gpu_snapshot
    os.environ.update(HF_HUB_OFFLINE='1',HF_DATASETS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    library=WORKSPACE/'.venv-wlk/Lib/site-packages/torch/lib'
    os.environ['PATH']=str(library)+os.pathsep+os.environ['PATH']
    dll=os.add_dll_directory(str(library)) if hasattr(os,'add_dll_directory') else None
    evidence=Path(evidence);evidence.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((WORKSPACE/'logs/trad_lab/m5a_20261020T201327Z/gpu_r1/cached_models.json').read_text(encoding='utf-8'))
    cache=manifest['large-v3-turbo']
    if cache['status']!='available':raise RuntimeError('Evaluated Turbo cache unavailable; no download')
    for name,sha in cache['files'].items():
        if digest(Path(cache['snapshot'])/name)!=sha:raise ValueError('Turbo model changed')
    if float(gpu_snapshot()['free_mib'])<3500:raise RuntimeError('Insufficient initial GPU reserve')
    from faster_whisper import WhisperModel
    from faster_whisper.utils import get_assets_path
    if digest(Path(get_assets_path())/'silero_vad_v6.onnx')!='4cbf549b8326f60f80f2536d9eefeb450a9abe83365a098031c89719f1be17d2':raise ValueError('VAD changed')
    model=WhisperModel(cache['snapshot'],device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
    if model.model.compute_type!='float16':raise RuntimeError('Unexpected precision')
    list(model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)[0])
    (evidence/'profile.json').write_text(json.dumps({'options':OPTIONS,'cache':cache,'effective_precision':model.model.compute_type,
       'warmup':'0.5 s zeros, VAD OFF as M5-A, excluded','environment':environment(),'gpu_before_work':gpu_snapshot()},indent=2),encoding='utf-8')
    def decode(audio,start):
        segments,info=model.transcribe(audio,**OPTIONS)
        return [Word(w.word,start+w.start,start+w.end,w.probability) for s in segments for w in s.words or []]
    decode._dll=dll;decode._model=model
    return decode

"""Post-session small comparison on exact recorded/replayed bytes; no WER.

Run only after shutting down both authorized lab services. Each model remains
sequential, cached-only. An OOM terminates this attempt without profile retries.
"""
import json
import os
from pathlib import Path
from dataclasses import asdict
import time

from .prepare import private_path, digest


def offline(capture,out):
    from .server import listening
    if any(listening(p) for p in (8000,8010,18000,18010)):raise RuntimeError('All GPU/lab services must be closed before offline analysis')
    capture=Path(capture).resolve();out=private_path(out);out.mkdir(parents=True,exist_ok=False)
    analysis=json.loads((capture/'analysis.json').read_text(encoding='utf-8'))
    if not analysis['integrity']['three_way_sha256_equal']:raise ValueError('Unverified transport')
    # Caller must run deterministic replay first; original output MUST match
    # the captured baseline byte-for-byte before comparing the candidate.
    replay=capture/'replay';info=json.loads(replay.with_suffix('.json').read_text())
    original=Path(str(replay)+'.original.s16le');candidate=Path(str(replay)+'.candidate.s16le')
    if digest(original)!=analysis['integrity']['sent']['sha256']:raise ValueError('Original replay differs from captured baseline')
    if digest(candidate)!=info['candidate_sha256']:raise ValueError('Candidate replay changed')
    os.environ.update(HF_HUB_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    os.environ['PATH']='C:/live-captions/.venv-wlk/Lib/site-packages/torch/lib'+os.pathsep+os.environ['PATH']
    from trad_lab.m4.experiments import cached_models, Monitor
    from trad_lab.runner import DECODE, environment
    from trad_lab.metrics import metrics
    from faster_whisper import WhisperModel
    import numpy as np
    encoder,_=cached_models();status={'status':'running'};results={}
    try:
        with Monitor(out/'gpu_samples.jsonl') as monitor:
            monitor.check()
            model=WhisperModel(str(encoder),device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
            # Two deterministic signal paths, the identical decoder profile.
            for name,path in [('exact_sent',original),('candidate_replay',candidate)]:
                monitor.check();audio=np.fromfile(path,dtype='<i2').astype('float32')/32768
                start=time.perf_counter();segments,meta=model.transcribe(audio,**DECODE)
                raw=[]
                for segment in segments:monitor.check();raw.append(asdict(segment))
                elapsed=time.perf_counter()-start
                results[name]={'hypothesis_raw':''.join(s['text'] for s in raw).strip(),'segments':raw,
                    'pcm_sha256':digest(path),'samples':len(audio),'audio_s':len(audio)/16000,
                    'asr_s':elapsed,'rtf':elapsed/(len(audio)/16000),'clinical_wer':None}
            raw=analysis['text']['raw_before_segment_manager'];ready=analysis['text']['ready_after_segment_manager']
            results['disagreement']={'scope':'Hypothesis differences, not accuracy WER',
                'offline_same_pcm_vs_wlk':metrics(results['exact_sent']['hypothesis_raw'],raw),
                'wlk_vs_ready':metrics(raw,ready),
                'original_vs_candidate_offline':metrics(results['exact_sent']['hypothesis_raw'],results['candidate_replay']['hypothesis_raw'])}
        status={'status':'completed'}
    except Exception as exc:
        status={'status':'blocked','reason':type(exc).__name__,'oom': 'out of memory' in str(exc).lower(),
                'policy':'No automatic precision/model/package/retry changes; retain partial evidence'}
        raise
    finally:
        (out/'result.json').write_text(json.dumps({'status':status,'environment':environment(),
            'profile':DECODE,'compute_type':'float16','model':'small','results':results},indent=2,ensure_ascii=False,default=str),encoding='utf-8')

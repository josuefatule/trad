"""Installed alternative, isolated fixed-chunk replay. Never replaces LIVE."""
from dataclasses import asdict
import json
import logging
from pathlib import Path
import statistics
import time

from trad_lab.runner import save,environment
from .audio_analysis import read_pcm
from .experiments import Monitor,cached_models,load_samples,score,WarningCapture


def run(args):
    import numpy as np
    from whisperlivekit.local_agreement.whisper_online import backend_factory
    from whisperlivekit.local_agreement.online_asr import OnlineASRProcessor
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    samples=load_samples(args.clips);glossary=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
    with Monitor(out/'gpu_samples.jsonl') as monitor:
        encoder,_=cached_models()
        asr=backend_factory(backend='faster-whisper',lan='en',model_size='small',model_cache_dir=None,
            model_dir=str(encoder),model_path=None,lora_path=None,direct_english_translation=False,
            buffer_trimming='segment',buffer_trimming_sec=15.,confidence_validation=False,warmup_file='')
        if str(asr.model.model.device)!='cuda':raise RuntimeError('Alternative requires CUDA; no fallback')
        asr.transcribe(np.zeros(8000,dtype='float32'))
        save(out/'environment.json',{**environment(),'policy':'installed LocalAgreement','beam_size':5,
            'effective_compute_type':asr.model.model.compute_type,'language':asr.original_language,'chunk_s':1.,
            'buffer_trimming':'segment','buffer_trimming_sec':15.,'confidence_validation':False,
            'scope':'Alternative architecture fixed-chunk replay, not a one-variable causal comparison to AlignAtt or offline float16. No VAD/VAC, server, DOM or DeepL.'})
        logger=logging.getLogger('whisperlivekit');warnings=WarningCapture();logger.addHandler(warnings)
        try:
            for repeat in range(args.repeats):
                for sample in samples:
                    monitor.check();processor=OnlineASRProcessor(asr);audio=read_pcm(sample['wav_path']).astype('float32')
                    events=[];words=[];lags=[];compute=0.;begin_warnings=len(warnings.messages)
                    for offset in range(0,len(audio),16000):
                        monitor.check();end=min(len(audio),offset+16000);processor.insert_audio_chunk(audio[offset:end],end/16000)
                        before=time.perf_counter();emitted,processed=processor.process_iter();wall=time.perf_counter()-before;compute+=wall
                        values=[asdict(t) for t in emitted];words.extend(values)
                        pending=processor.get_buffer().text
                        events.append({'audio_available_s':end/16000,'compute_s':wall,'tokens':values,'pending':pending})
                        lags.extend(end/16000-float(t.end) for t in emitted)
                    tail,_=processor.finish();tail_values=[asdict(t) for t in tail];words.extend(tail_values)
                    text=''.join(w['text'] for w in words)
                    result={'sample':sample['id'],'family':'local_agreement_fixed_chunk','beam':5,'repeat':repeat,
                        'wav_sha256':sample['wav_sha256'],'hypothesis_raw':text,'events':events,'eof_unconfirmed_tail':tail_values,
                        'audio_s':len(audio)/16000,'asr_wall_s':compute,'rtf':compute/(len(audio)/16000),
                        'commit_lag_median_s':statistics.median(lags) if lags else None,'commit_lag_max_s':max(lags) if lags else None,
                        'latency_scope':'Algorithmic availability minus ASR token-end estimate, fixed 1 s chunks; no browser paint or real-time queue measurement',
                        'warnings':warnings.messages[begin_warnings:],**score(sample,text,glossary)}
                    save(out/f"{sample['id']}.r{repeat}.json",result)
                    print(json.dumps({'family':result['family'],'sample':sample['id'],'repeat':repeat,'wer':result['accuracy']['wer'] if result['accuracy'] else None,'rtf':result['rtf']}),flush=True)
        finally:logger.removeHandler(warnings)
        monitor.check()
    save(out/'gpu_samples.json',{'samples':monitor.samples})

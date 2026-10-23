"""Cached-only GPU experiments; decoder replay is not a server or LIVE test."""
from contextlib import AbstractContextManager
from copy import copy
from dataclasses import asdict
import gc
import json
import logging
import os
from pathlib import Path
import statistics
import threading
import time

from trad_lab.audio import digest
from trad_lab.metrics import metrics,term_inventory
from trad_lab.runner import DECODE,environment,save
from trad_lab.safety import LiveGuard,gpu_snapshot
from .audio_analysis import read_pcm
from .references import validated_reference


class Monitor(AbstractContextManager):
    def __init__(self,path=None):self.samples=[];self.unsafe=None;self.done=threading.Event();self.guard=LiveGuard();self.path=path
    def check(self):
        if self.unsafe:raise RuntimeError('Safety guard stopped own experiment: '+json.dumps(self.unsafe))
    def _poll(self):
        while not self.done.is_set():
            try:
                state=self.guard.check()
                if not state['safe']:self.unsafe=state
                sample={'at':time.monotonic(),**gpu_snapshot()};self.samples.append(sample)
                if float(sample['free_mib'])<768:self.unsafe={'reason':'VRAM reserve exhausted'}
                if self.path:
                    with Path(self.path).open('a',encoding='utf-8') as f:f.write(json.dumps(sample)+'\n')
            except Exception as exc:self.unsafe={'reason':type(exc).__name__}
            self.done.wait(1)
    def __enter__(self):
        state=self.guard.check()
        if not state['safe']:raise RuntimeError('Production active/unknown; no GPU work')
        self.thread=threading.Thread(target=self._poll,daemon=True);self.thread.start();return self
    def __exit__(self,*args):self.done.set();self.thread.join(timeout=12)


def cached_models():
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    from faster_whisper.utils import download_model
    encoder=Path(download_model('small',local_files_only=True))
    decoder=Path.home()/'.cache/whisper/small.pt'
    if not decoder.is_file():raise RuntimeError('PyTorch small weights absent; download requires separate authorization')
    if digest(decoder)!='9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794':
        raise RuntimeError('Cached decoder differs from M3; re-audit before use')
    return encoder,decoder


def load_samples(clips):
    path=Path(clips);samples=json.loads(path.read_text(encoding='utf-8'))
    validation=json.loads((path.parent/'reference_validation.json').read_text(encoding='utf-8'))
    for s in samples:
        if digest(s['wav_path'])!=s['wav_sha256']:raise ValueError('Input WAV changed')
        s['reference']=validated_reference(s,validation)
    return samples


def score(sample,text,glossary):
    reference=sample['reference']
    return {'accuracy':metrics(reference,text) if reference is not None else None,
        'term_inventory':term_inventory(reference,text,glossary['terms']) if reference is not None else None,
        'reference_status':'user-accepted provisional temporal reference; boundary spread retained' if reference is not None else 'BLOCKED: temporal reference unvalidated',
        'boundary_spread_s':sample['boundary_spread_s']}


def offline(args):
    import numpy as np
    from faster_whisper import WhisperModel
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    samples=load_samples(args.clips);glossary=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
    with Monitor(out/'gpu_samples.jsonl') as monitor:
        encoder,_=cached_models();monitor.check()
        if float(gpu_snapshot()['free_mib'])<1800:raise RuntimeError('Insufficient VRAM reserve')
        start=time.perf_counter();model=WhisperModel(str(encoder),device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
        load_s=time.perf_counter()-start
        list(model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)[0])
        save(out/'environment.json',{**environment(),'model_snapshot':str(encoder),'load_s':load_s,
            'effective_compute_type':model.model.compute_type,'decode_base':DECODE,'only_varied':'beam_size; repeat order alternated'})
        for rep in range(args.repeats):
            for beam in ([1,5] if rep%2==0 else [5,1]):
                options={**DECODE,'beam_size':beam,'initial_prompt':None,'hotwords':None}
                for sample in samples:
                    monitor.check();audio=read_pcm(sample['wav_path']).astype('float32')
                    begin=time.perf_counter();generated,info=model.transcribe(audio,**options)
                    segments=[asdict(s) for s in generated];wall=time.perf_counter()-begin
                    text=''.join(s['text'] for s in segments)
                    result={'sample':sample['id'],'family':'faster_whisper_offline','beam':beam,'repeat':rep,
                        'wav_sha256':sample['wav_sha256'],'hypothesis_raw':text,'segments':segments,'decoding':options,
                        'asr_wall_s':wall,'audio_s':len(audio)/16000,'rtf':wall/(len(audio)/16000),
                        'timing_scope':'offline generator fully consumed; excludes load/warmup/decode/scoring; not visible streaming latency',
                        'gpu_at_end':gpu_snapshot(),**score(sample,text,glossary)}
                    save(out/f"{sample['id']}.beam{beam}.r{rep}.json",result)
                    print(json.dumps({'family':result['family'],'sample':sample['id'],'beam':beam,'repeat':rep,'wer':result['accuracy']['wer'] if result['accuracy'] else None}),flush=True)
        monitor.check()
    save(out/'gpu_samples.json',{'samples':monitor.samples,'scope':'total device sampled every ~1 s including query/guard overhead; not exact allocator peak'})


class WarningCapture(logging.Handler):
    def __init__(self):super().__init__(logging.WARNING);self.messages=[]
    def emit(self,record):self.messages.append(record.getMessage())


def simul(args):
    import numpy as np
    import torch
    from whisperlivekit.config import WhisperLiveKitConfig
    from whisperlivekit.simul_whisper.backend import SimulStreamingASR,SimulStreamingOnlineProcessor
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    samples=load_samples(args.clips);glossary=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
    torch.set_num_threads(4)
    logging.getLogger('whisperlivekit.simul_whisper').setLevel(logging.WARNING)
    with Monitor(out/'gpu_samples.jsonl') as monitor:
        encoder,decoder=cached_models();monitor.check()
        if float(gpu_snapshot()['free_mib'])<3000:raise RuntimeError('Insufficient streaming VRAM reserve')
        config=WhisperLiveKitConfig(backend='faster-whisper',model_size='small',lan='en',pcm_input=True,
            warmup_file='',encoder_model_path=str(encoder),decoder_model_path=str(decoder))
        start=time.perf_counter();backend=SimulStreamingASR(**asdict(config));load_s=time.perf_counter()-start
        if next(backend.shared_model.parameters()).device.type!='cuda':raise RuntimeError('CUDA required; no CPU fallback')
        warm=SimulStreamingOnlineProcessor(backend);warm.warmup(torch.zeros(16000));torch.cuda.synchronize();del warm
        gc.collect();torch.cuda.empty_cache()
        save(out/'environment.json',{**environment(),'configuration':asdict(config),'effective_base_cfg':asdict(backend.cfg),
            'encoder_compute_type':backend.fw_encoder.model.compute_type,'decoder_parameter_dtype':str(next(backend.shared_model.parameters()).dtype),
            'decoder_path':str(decoder),'decoder_sha256':digest(decoder),'model_load_s':load_s,
            'chunk_s':args.chunk_s,'only_varied':'AlignAttConfig.beam_size; shared cached weights and other config identical',
            'scheduling':'CUDA synchronized before/after each fixed chunk; accelerated replay, not real-time pacing',
            'scope':'Direct installed SimulStreamingOnlineProcessor fixed-PCM replay. No VAD/VAC, WebSocket, audio coalescing, TRAD session, DOM or DeepL. Not a full WLK server benchmark.'})
        logger=logging.getLogger('whisperlivekit.simul_whisper.backend');warnings=WarningCapture();logger.addHandler(warnings)
        try:
            for rep in range(args.repeats):
                for beam in ([1,5] if rep%2==0 else [5,1]):
                    for sample in samples:
                        monitor.check();local=copy(backend);local.cfg=copy(backend.cfg);local.cfg.beam_size=beam
                        processor=SimulStreamingOnlineProcessor(local)
                        if (processor.model.cfg.beam_size!=beam or processor.model.tokenizer.language!='en'
                                or processor.model.decode_options.language!='en'):raise RuntimeError('Effective decoder profile mismatch')
                        audio=read_pcm(sample['wav_path']).astype('float32');events=[];words=[];warning_start=len(warnings.messages)
                        chunk=round(args.chunk_s*16000);start=time.perf_counter();compute=0.;lags=[]
                        for offset in range(0,len(audio),chunk):
                            monitor.check();end=min(len(audio),offset+chunk);block=audio[offset:end]
                            before=time.perf_counter();processor.insert_audio_chunk(block,end/16000)
                            torch.cuda.synchronize()
                            emitted,processed=processor.process_iter(is_last=end==len(audio));torch.cuda.synchronize()
                            elapsed=time.perf_counter()-before;compute+=elapsed
                            if any('processing error' in m.casefold() for m in warnings.messages[warning_start:]):
                                raise RuntimeError('Decoder reported an internal error; no completed metrics may be emitted')
                            values=[asdict(t) for t in emitted];words.extend(values)
                            events.append({'audio_available_s':end/16000,'compute_s':elapsed,'wall_elapsed_s':time.perf_counter()-start,'tokens':values,'processed_upto':processed,
                                'torch_allocated_mib':torch.cuda.memory_allocated()/2**20,'torch_reserved_mib':torch.cuda.memory_reserved()/2**20})
                            lags.extend(end/16000-float(t.end) for t in emitted)
                        text=''.join(w['text'] for w in words);wall=time.perf_counter()-start
                        result={'sample':sample['id'],'family':'simul_fixed_chunk_replay','beam':beam,'repeat':rep,
                            'wav_sha256':sample['wav_sha256'],'hypothesis_raw':text,'events':events,'effective_cfg':asdict(processor.model.cfg),
                            'audio_s':len(audio)/16000,'asr_wall_s':compute,'total_replay_wall_s':wall,'rtf':compute/(len(audio)/16000),
                            'commit_lag_median_s':statistics.median(lags) if lags else None,'commit_lag_max_s':max(lags) if lags else None,
                            'latency_scope':'Algorithmic audio-available minus ASR-estimated token end, fixed chunks. Not wall-clock visible latency; negative values retained.',
                            'incremental_scope':'Committed tokens only; reset/drop warnings retained. Append-only output is not proof of absence of internal revisions.',
                            'warnings':warnings.messages[warning_start:],'gpu_at_end':gpu_snapshot(),**score(sample,text,glossary)}
                        save(out/f"{sample['id']}.beam{beam}.r{rep}.json",result)
                        print(json.dumps({'family':result['family'],'sample':sample['id'],'beam':beam,'repeat':rep,'wer':result['accuracy']['wer'] if result['accuracy'] else None,'rtf':result['rtf']}),flush=True)
                        del processor;gc.collect();torch.cuda.empty_cache()
        finally:logger.removeHandler(warnings)
        monitor.check()
    save(out/'gpu_samples.json',{'samples':monitor.samples,'scope':'Total device, includes model residency and Windows; ~1 s samples may miss short peaks'})

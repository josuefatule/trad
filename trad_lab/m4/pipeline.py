"""Installed full WLK AudioProcessor paced replay, without an HTTP server.

Preserves VAC/VAD/coalescing and the session-language factory. This measures
ASR response arrival in process; it never claims browser/OBS visible latency.
"""
import asyncio
from copy import copy
from dataclasses import asdict
import gc
import json
import logging
from pathlib import Path
import time

from app.asr.wlk_server import isolated_factory
from app.captions.transcript_state import TranscriptState
from trad_lab.runner import environment,save
from .audio_analysis import read_pcm
from .experiments import Monitor,cached_models,load_samples,score,WarningCapture


async def run(args):
    import numpy as np
    import torch
    from whisperlivekit import audio_processor,core
    from whisperlivekit.config import WhisperLiveKitConfig
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    samples=load_samples(args.clips);glossary=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
    torch.set_num_threads(4)
    logging.getLogger('whisperlivekit').setLevel(logging.WARNING)
    with Monitor(out/'gpu_samples.jsonl') as monitor:
        encoder,decoder=cached_models();monitor.check()
        config=WhisperLiveKitConfig(backend='faster-whisper',model_size='small',lan='en',pcm_input=True,
            warmup_file='',encoder_model_path=str(encoder),decoder_model_path=str(decoder))
        engine=core.TranscriptionEngine(config=config)
        selected_beam=1;base=isolated_factory(audio_processor.online_factory)
        def factory(options,asr,language=None):
            local=copy(asr);local.cfg=copy(asr.cfg);local.cfg.beam_size=selected_beam
            return base(options,local,language)
        audio_processor.online_factory=factory
        save(out/'environment.json',{**environment(),'configuration':asdict(config),
            'scope':'Paced mono s16 PCM into installed AudioProcessor, VAC/VAD and language factory. No HTTP/WebSocket/Operator/CAPTURE/DOM/DeepL.',
            'pacing':'1600 samples every 100 ms; deadline anchored to monotonic start; EOF and full results drain',
            'only_varied':'constructed AlignAttConfig.beam_size (1 vs 5); same PCM bytes and all remaining options',
            'encoder_compute_type':engine.asr.fw_encoder.model.compute_type,'decoder_parameter_dtype':str(next(engine.asr.shared_model.parameters()).dtype)})
        logger=logging.getLogger('whisperlivekit');warnings=WarningCapture();logger.addHandler(warnings)
        try:
            for repeat in range(args.repeats):
                for beam in ([1,5] if repeat%2==0 else [5,1]):
                    selected_beam=beam
                    for sample in samples:
                        monitor.check();processor=audio_processor.AudioProcessor(transcription_engine=engine,language='en',mode='full',pcm_input=True)
                        decoder=processor.transcription.model
                        if decoder.cfg.beam_size!=beam or decoder.tokenizer.language!='en':raise RuntimeError('Decoder contract mismatch')
                        audio=read_pcm(sample['wav_path']);pcm=(np.rint(audio*32768)).astype('<i2').tobytes()
                        state=TranscriptState();events=[];sent=0;start=time.monotonic();begin_warnings=len(warnings.messages)
                        filename=f"{sample['id']}.beam{beam}.r{repeat}"
                        generator=await processor.create_tasks()
                        async def produce():
                            nonlocal sent
                            for offset in range(0,len(pcm),3200):
                                monitor.check();block=pcm[offset:offset+3200]
                                await asyncio.sleep(max(0,start+offset/32000-time.monotonic()))
                                await processor.process_audio(block);sent+=len(block)
                                save(out/'progress.json',{'sample':sample['id'],'beam':beam,'repeat':repeat,'sent_s':sent/32000})
                            await processor.process_audio(b'')
                        async def consume():
                            async for response in generator:
                                monitor.check();payload=response.to_dict();state.update(payload)
                                event={'at_s':time.monotonic()-start,'audio_sent_s':sent/32000,'payload':payload,
                                    'confirmed_text':state.confirmed_text,'partial_text':state.partial_text}
                                events.append(event)
                                with (out/(filename+'.events.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps(event,ensure_ascii=False)+'\n')
                        try:
                            async with asyncio.timeout(len(audio)/16000+120):await asyncio.gather(produce(),consume())
                            monitor.check()
                            errors=[m for m in warnings.messages[begin_warnings:] if 'processing error' in m.casefold() or 'exception in transcription' in m.casefold()]
                            if errors:raise RuntimeError('Internal decoder errors; result is incomplete')
                            result={'sample':sample['id'],'family':'wlk_paced_pipeline','beam':beam,'repeat':repeat,
                                'wav_sha256':sample['wav_sha256'],'hypothesis_raw':state.confirmed_text,'events':events,
                                'effective_cfg':asdict(decoder.cfg),'audio_s':len(audio)/16000,'wall_s':time.monotonic()-start,
                                'pcm_samples_sent':sent//2,'input_pcm_samples':len(audio),'eof_drained':True,
                                'session_metrics':asdict(processor.metrics),'warnings':warnings.messages[begin_warnings:],
                                'latency_scope':'In-process ASR responses, paced audio. No browser paint/OBS/translation latency.',
                                'gpu_at_end':__import__('trad_lab.safety',fromlist=['gpu_snapshot']).gpu_snapshot(),**score(sample,state.confirmed_text,glossary)}
                            save(out/(filename+'.json'),result)
                            print(json.dumps({'family':result['family'],'sample':sample['id'],'beam':beam,'repeat':repeat,'wer':result['accuracy']['wer'] if result['accuracy'] else None}),flush=True)
                        finally:
                            await processor.cleanup();del processor;gc.collect();torch.cuda.empty_cache()
        finally:logger.removeHandler(warnings)
    save(out/'gpu_samples.json',{'samples':monitor.samples,'scope':'Device-wide ~1 s samples plus query/guard overhead, not exact process peak'})

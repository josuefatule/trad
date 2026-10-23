"""Cached small/CUDA causal file replay. Run only with all four services closed."""
import argparse
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
import shutil
from pathlib import Path
import time
import wave
import numpy as np
from trad_lab.audio import digest
from trad_lab.metrics import metrics, tokens
from trad_lab.m4.experiments import Monitor, cached_models, load_samples
from trad_lab.m4b.server import listening
from trad_lab.runner import DECODE, environment
from trad_lab.safety import gpu_snapshot
from .incremental import Config, HorizonError, Incremental, Word

ROOT = Path(__file__).resolve().parents[2]
SAVED = ROOT/'logs/trad_lab/m4b_saved_analysis_20261020T170153Z'
PAIR = ROOT/'logs/trad_lab/m4b_pair_20261020T164150Z'
ENV = ROOT/'logs/trad_lab/m4b_openerfix_20261020T161600Z/environment_opener_ready'


class ClosedServices:
    def check(self):
        occupied = [p for p in (8000,8010,18000,18010) if listening(p)]
        return {'safe':not occupied,'reason':'all_services_closed' if not occupied else 'occupied_ports','ports':occupied}


def save(path, value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')


def datasets(group):
    if group == 'yeti':
        p=ENV/'trad_wire/wire_01/received.s16le'
        expected='d482dead07ea58555bb5a478fcb95c1ea2eccef346153a636464f1023060809d'
        assert digest(p)==expected and digest(ENV/'wlk_wire/wire_01/received.s16le')==expected
        return [{'id':'yeti_received_full','path':str(p),'sha256':expected,'format':'s16le',
                 'reference':None,'reference_status':'No temporally aligned clinical reference',
                 'offline':str(SAVED/'received_full.json'),
                 'wlk':str(PAIR/'attempt03_server_text_analysis.json')}]
    if group == 'clips':
        data=load_samples(ROOT/'logs/trad_lab/m4_20261020T084747Z/references/clips.json')
        return [{**s,'path':s['wav_path'],'sha256':s['wav_sha256'],'format':'wav',
                 'reference_status':'M4 user-accepted provisional clip; boundary spread retained'} for s in data]
    data=json.loads((ROOT/'logs/trad_lab/20261020T074247Z/evaluation/inputs/inputs.json').read_text(encoding='utf-8'))
    result=[]
    for s in data:
        assert digest(s['audio_path'])==s['audio_sha256'] and digest(s['reference_path'])==s['reference_sha256']
        result.append({'id':s['id'],'path':s['wav_path'],'sha256':s['wav_sha256'],'format':'wav',
                       'reference':Path(s['reference_path']).read_text(encoding='utf-8-sig'),'reference_status':'Full MP3/TXT pair reviewed by user; provisional lexical score, not time-aligned clinical truth',
                       'offline':str(ROOT/f"logs/trad_lab/20261020T074247Z/evaluation/models/small/{s['id']}/result.json")})
    return result


@contextmanager
def pcm_reader(sample):
    assert digest(sample['path'])==sample['sha256']
    if sample['format']=='wav':
        with wave.open(sample['path'],'rb') as f:
            assert (f.getnchannels(),f.getsampwidth(),f.getframerate())==(1,2,16000)
            yield f.readframes, f.getnframes()
    else:
        with open(sample['path'],'rb') as f:
            assert Path(sample['path']).stat().st_size%2==0
            yield lambda n:f.read(n*2), Path(sample['path']).stat().st_size//2


def distribution(values):
    return {'n':len(values),'median':float(np.median(values)) if values else None,
            'p95':float(np.percentile(values,95)) if values else None,
            'min':min(values) if values else None,'max':max(values) if values else None}


def run_sample(model, sample, config, out, monitor, decode_options=None):
    options=decode_options or {**DECODE,'initial_prompt':None,'hotwords':None}
    out.mkdir(parents=True,exist_ok=False)
    committed=[]; events=[]; available=0; decoder_metadata={}
    with (out/'events.jsonl').open('w',encoding='utf-8') as log:
        def sink(event):
            if event['type']=='update':event['decoder_metadata']=dict(decoder_metadata)
            log.write(json.dumps(event,ensure_ascii=False)+'\n');log.flush()
            events.append(event)
            committed.extend(event.get('confirmed',[]))
        def decode(audio, start):
            monitor.check()
            segments,info=model.transcribe(audio,**options)
            result=[]
            for segment in segments:
                for w in segment.words or []:
                    result.append(Word(w.word,start+w.start,start+w.end,w.probability))
            decoder_metadata.update({'input_duration_s':info.duration,'duration_after_vad_s':info.duration_after_vad,
                                     'language':info.language})
            monitor.check()
            return result
        engine=Incremental(decode,sink,config)
        begin=time.perf_counter();status='completed';error=None;stats=None
        try:
            with pcm_reader(sample) as (read,total):
                while True:
                    raw=read(round(config.update_s*16000))
                    if not raw:break
                    available+=len(raw)//2
                    engine.push(np.frombuffer(raw,dtype='<i2').astype('float32')/32768.)
                stats=engine.finish()
        except Exception as exc:
            status='failed';error={'type':type(exc).__name__,'message':str(exc)}
            sink({'type':'failure','received_samples':available,'error':error})
            if not isinstance(exc,HorizonError) or monitor.unsafe:
                save(out/'abort.json',{'sample':sample['id'],'error':error,'received_samples':available,
                                       'policy':'Unexpected decoder/integrity/GPU error aborts the batch; no automatic fallback/retry'})
                raise
        wall=time.perf_counter()-begin
    tail=[asdict(w) for w in engine.pending]
    stable_text=''.join(w['text'] for w in committed)
    final_text=stable_text+''.join(w['text'] for w in tail)
    lags=[];serial_lags=[];first_lags=[]
    sightings_by_word={}
    for event in events:
        for word in event.get('hypothesis',[]):
            key=tuple(tokens(word['text']))
            sightings_by_word.setdefault(key,[]).append((word['end'],event['available_s']))
    for event in events:
        for w in event.get('confirmed',[]):
            lags.append(event['available_s']-w['end'])
            serial_lags.append(event['serial_completion_s']-w['end'])
            sightings=[at for end,at in sightings_by_word.get(tuple(tokens(w['text'])),[])
                       if at<=event['available_s'] and abs(end-w['end'])<=config.timestamp_tolerance_s]
            if sightings:first_lags.append(min(sightings)-w['end'])
    result={'status':status,'error':error,'sample':sample,'config':asdict(config),'decoding':options,
            'stats':stats,'audio_s':total/16000,'processed_s':available/16000,'replay_wall_s':wall,
            'inference_rtf':engine.compute_s/(available/16000) if available else None,
            'stable_text':stable_text,'eof_tail_text':''.join(w['text'] for w in tail),
            'final_text_with_unconfirmed_eof_tail':final_text,'commits':committed,
            'stable_word_count':len(tokens(stable_text)),'final_word_count':len(tokens(final_text)),
            'confirmation_lag_s':distribution(lags),'serial_confirmation_lag_s':distribution(serial_lags),
            'first_hypothesis_lag_s':distribution(first_lags),
            'timing_scope':'Accelerated causal replay. Available sample index /16000; lag relative to candidate ASR-estimated word end, not independently aligned speech. Serial completion models one decoder with no queue drops, using measured perf_counter durations. Excludes network/DOM/DeepL.',
            'immutable_confirmation':'Engine emits append-only commits; provisional revisions allowed; EOF tail explicitly unconfirmed',
            'peak_audio_samples':engine.peak_samples,'peak_word_state':engine.peak_words,'calls':engine.calls}
    if status=='completed':
        if sample.get('reference') is not None:
            result['provisional_reference_metrics']=metrics(sample['reference'],final_text)
            result['stable_only_reference_metrics']=metrics(sample['reference'],stable_text)
        if sample.get('offline'):
            baseline=json.loads(Path(sample['offline']).read_text(encoding='utf-8'))['hypothesis_raw']
            result['offline_hypothesis_disagreement']=metrics(baseline,final_text)
        if sample.get('wlk'):
            baseline=json.loads(Path(sample['wlk']).read_text(encoding='utf-8'))['raw_before_segment_manager']
            result['wlk_hypothesis_disagreement']=metrics(baseline,final_text)
    save(out/'result.json',result)
    print(json.dumps({'sample':sample['id'],'config':asdict(config),'status':status,'processed_s':available/16000,
                      'error':error,'words':len(tokens(final_text)),
                      'reference_wer':result.get('provisional_reference_metrics',{}).get('wer'),
                      'offline_disagreement':result.get('offline_hypothesis_disagreement',{}).get('wer'),
                      'rtf':result['inference_rtf']}),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',required=True)
    parser.add_argument('--group',choices=['yeti','clips','full'],required=True)
    parser.add_argument('--windows',type=float,nargs='+',default=[5,10,15])
    parser.add_argument('--update',type=float,default=2)
    parser.add_argument('--agreement',type=int,default=2)
    parser.add_argument('--vad',action='store_true',help='Independent experiment: installed Silero defaults, no downloads')
    parser.add_argument('--beam',type=int,choices=[1,5],default=5)
    parser.add_argument('--only',nargs='+',help='Explicit subset; never aggregate as the full corpus')
    parser.add_argument('--mode',choices=['fixed','adaptive'],default='fixed')
    parser.add_argument('--minimum-age',type=float,default=1,help='Minimum age of a confirmed word in available-audio seconds')
    args=parser.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    frozen=out/'sources';frozen.mkdir()
    for source in Path(__file__).parent.glob('*.py'):
        shutil.copyfile(source,frozen/source.name)
    save(out/'source_hashes.json',{p.name:digest(p) for p in frozen.glob('*.py')})
    os.environ['HF_DATASETS_OFFLINE']='1'
    torch_lib=ROOT/'.venv-wlk/Lib/site-packages/torch/lib'
    os.environ['PATH']=str(torch_lib)+os.pathsep+os.environ['PATH']
    if hasattr(os,'add_dll_directory'):dll=os.add_dll_directory(str(torch_lib))
    from faster_whisper import WhisperModel
    monitor=Monitor(out/'gpu.jsonl');monitor.guard=ClosedServices()
    with monitor:
        if float(gpu_snapshot()['free_mib'])<2200:raise RuntimeError('Insufficient initial VRAM reserve')
        encoder,_=cached_models()
        model=WhisperModel(str(encoder),device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
        assert model.model.compute_type=='float16'
        list(model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)[0])
        options={**DECODE,'initial_prompt':None,'hotwords':None,'vad_filter':args.vad,'beam_size':args.beam}
        vad_details=None
        if args.vad:
            from faster_whisper.vad import VadOptions
            from faster_whisper.utils import get_assets_path
            path=Path(get_assets_path())/'silero_vad_v6.onnx'
            if not path.is_file():raise RuntimeError('Packaged VAD absent; no download permitted')
            vad_details={'file':str(path),'sha256':digest(path),'options':{k:(str(v) if isinstance(v,float) and not np.isfinite(v) else v) for k,v in asdict(VadOptions()).items()}}
        save(out/'environment.json',{'environment':environment(),'effective_compute_type':model.model.compute_type,
             'model_snapshot':str(encoder),'decoding':options,'vad':vad_details,'config_args':vars(args),'gpu_scope':'Total device samples, not exact allocator peak'})
        samples=datasets(args.group)
        if args.only:
            samples=[s for s in samples if s['id'] in args.only]
            if len(samples)!=len(set(args.only)):raise ValueError('Unknown or duplicate sample selection')
        for window in args.windows:
            config=Config(window_s=window,update_s=args.update,agreement=args.agreement,mode=args.mode,minimum_age_s=args.minimum_age)
            for sample in samples:
                suffix='_adaptive' if args.mode=='adaptive' else ''
                run_sample(model,sample,config,out/f"w{window:g}_u{args.update:g}_a{args.agreement}{suffix}"/sample['id'],monitor,options)
        monitor.check()
    save(out/'gpu_summary.json',{'samples':len(monitor.samples),'peak_used_mib':max(float(s['used_mib']) for s in monitor.samples),
                                 'min_free_mib':min(float(s['free_mib']) for s in monitor.samples)})


if __name__=='__main__':main()

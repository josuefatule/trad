"""Cached-only M4-D experiments; raw outputs never become reference text."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import wave
import numpy as np
from trad_lab.audio import digest
from trad_lab.runner import DECODE, environment, save
from trad_lab.safety import gpu_snapshot
from trad_lab.m4.experiments import Monitor
from trad_lab.m4c.replay import ClosedServices, datasets, run_sample
from trad_lab.m4c.incremental import Config

ROOT=Path(__file__).resolve().parents[2]
PRIOR=ROOT/'logs/trad_lab/m4c_20261020T173100Z'
M3=ROOT/'logs/trad_lab/20261020T074247Z/evaluation'
CASES={
 'cardio01_orthostatic':('ORTHO','orthostatic hypotension'),
 'cardio03_untreated':('UNTREATED','untreated stage two hypertension'),
 'cardio03_years':('YEARS','every four to six years'),
 'cardio01_140':('BP140','140 over 90'),
}
MODELS=('small','medium','large-v3-turbo')

def read_wav(path):
    with wave.open(str(path),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):
            raise ValueError('Expected mono s16 16 kHz')
        return f.readframes(f.getnframes())

def source_pcm(path):
    return read_wav(path) if Path(path).suffix=='.wav' else Path(path).read_bytes()

def write_excerpt(source,start,end,out):
    raw=source_pcm(source)
    if not 0<=start<end<=len(raw)//2:raise ValueError('Excerpt bounds')
    with wave.open(str(out),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000)
        f.writeframes(raw[start*2:end*2])
    if read_wav(out)!=raw[start*2:end*2]:raise ValueError('PCM roundtrip mismatch')

def prepare(out):
    """Freeze user-adjudicated phrases BEFORE new model outputs are generated."""
    out.mkdir(parents=True,exist_ok=False)
    clips=out/'audio';clips.mkdir()
    manifest=json.loads((PRIOR/'review_audio_delivery/manifest.json').read_text(encoding='utf-8'))
    records=[];adjudication=[]
    for entry in manifest:
        path=Path(entry['file']);source=Path(entry['source'])
        if digest(path)!=entry['sha256'] or digest(source)!=entry['source_sha256']:
            raise ValueError('M4-C audio hash mismatch')
        start,end=entry['start_sample'],entry['end_sample']
        if read_wav(path)!=source_pcm(source)[start*2:end*2]:raise ValueError('Wrong excerpt')
        case=CASES.get(path.stem)
        record={**entry,'id':path.stem,'condition':'isolated','duration_s':(end-start)/16000,
                'case':case[0] if case else None}
        records.append(record)
        if case:
            adjudication.append({'case':case[0],'expression':case[1],'file':str(path),
                'sha256':digest(path),'source':str(source),'source_sha256':digest(source),
                'acoustic_container_start_s':start/16000,'acoustic_container_end_s':end/16000,
                'clip_start_s':0,'clip_end_s':(end-start)/16000,
                'expression_word_alignment':None,
                'authority':'Explicit user M4-D request: provisionally adjudicated by listening in conversation',
                'scope':'Expression only; NOT the entire clip sentence. Exact word boundaries not independently adjudicated.',
                'limitation':'This tool verifies PCM identity/bounds; it does not independently listen or infer reference from ASR.',
                'status':'user_provisional_expression'})
            left=max(0,start-160000);right=min(len(source_pcm(source))//2,end+160000)
            target=clips/(path.stem+'_context.wav')
            write_excerpt(source,left,right,target)
            records.append({**record,'id':path.stem+'_context','file':str(target),
                'sha256':digest(target),'condition':'context','start_sample':left,'end_sample':right,
                'duration_s':(right-left)/16000,'context_left_s':(start-left)/16000,
                'context_right_s':(right-end)/16000,'postcontext_scope':'Offline diagnostic only; no causal claim'})
    save(out/'adjudication.json',adjudication)
    save(out/'inputs.json',records)
    save(out/'selection_protocol.json',{
      'selection_cases':['ORTHO','UNTREATED','YEARS','BP140'],
      'context':'Exactly up to 10 s left and 10 s right, same recipe for all four; defined before inference',
      'incremental_baseline':'M4-C adaptive small, update 2 s, LA2, age 1 s, Silero defaults',
      'max_alternatives':2,'selection_priority':'Opposed diagnosis / treatment negation / range / blood pressure, before lexical WER',
      'checking':'Whole files replayed unchanged; regions outside selection context brackets are checking regions',
      'leakage':'Corpus was explored in M3/M4-C; checking is within-corpus regression, NOT an independent unseen test set. cardio02/03 may share one lecture.',
      'no_reference_context':True,'no_automatic_medical_correction':True})
    print(json.dumps({'verified_review_clips':len(manifest),'offline_inputs':len(records),'adjudicated_expressions':len(adjudication)}))

def caches(out):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    from faster_whisper.utils import download_model
    results={}
    for name in MODELS:
        try:
            path=Path(download_model(name,local_files_only=True))
            vocab='vocabulary.json' if (path/'vocabulary.json').is_file() else 'vocabulary.txt'
            required=('config.json','model.bin','tokenizer.json',vocab)
            if name=='large-v3-turbo':required+=('preprocessor_config.json',)
            if any(not (path/n).is_file() for n in required):raise FileNotFoundError('Incomplete CT2 snapshot')
            hashes={n:digest(path/n) for n in required}
            original=json.loads((M3/f'models/{name}/environment.json').read_text(encoding='utf-8'))
            if any(hashes[n]!=original['weight_manifest'][n]['sha256'] for n in required):
                raise ValueError('Model files differ from M3 evaluated snapshot')
            results[name]={'status':'available','snapshot':str(path),
                           'files':hashes,'matches_M3':True}
        except Exception as exc:
            results[name]={'status':'unavailable','error_type':type(exc).__name__,'message':str(exc)}
    save(out/'cached_models.json',results)
    return results

def configure_runtime():
    os.environ['HF_HUB_OFFLINE']='1';os.environ['HF_DATASETS_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    path=ROOT/'.venv-wlk/Lib/site-packages/torch/lib'
    os.environ['PATH']=str(path)+os.pathsep+os.environ['PATH']
    return os.add_dll_directory(str(path)) if hasattr(os,'add_dll_directory') else None

def model_session(name,folder,cache,work):
    from faster_whisper import WhisperModel
    folder.mkdir(parents=True,exist_ok=False)
    for package in ('m4c','m4d'):
        target=folder/'sources'/package;target.mkdir(parents=True)
        for source in (ROOT/'trad_lab'/package).glob('*.py'):
            shutil.copyfile(source,target/source.name)
    save(folder/'source_hashes.json',{str(p.relative_to(folder)):digest(p) for p in (folder/'sources').rglob('*.py')})
    monitor=Monitor(folder/'gpu.jsonl');monitor.guard=ClosedServices()
    with monitor:
        if float(gpu_snapshot()['free_mib'])<3500:raise RuntimeError('Initial VRAM reserve below 3500 MiB')
        started=time.perf_counter()
        model=WhisperModel(cache['snapshot'],device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
        if model.model.compute_type!='float16':raise RuntimeError('Unexpected effective precision')
        load=time.perf_counter()-started
        list(model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)[0])
        save(folder/'environment.json',{'environment':environment(),'model':name,'cache':cache,
            'effective_compute_type':model.model.compute_type,'load_s':load,'decoding':DECODE,
            'initial_prompt':None,'hotwords':None,'device':'cuda','warmup':'0.5 s zero input, excluded from experiments'})
        work(model,monitor)
        monitor.check()
    save(folder/'gpu_summary.json',{'samples':len(monitor.samples),
        'peak_used_mib':max(float(s['used_mib']) for s in monitor.samples),
        'min_free_mib':min(float(s['free_mib']) for s in monitor.samples),
        'max_temperature_c':max(float(s['temperature_c']) for s in monitor.samples),
        'scope':'Total GPU sampled nominally every second, not exact allocator peak'})

def offline(out,name):
    cache=json.loads((out/'cached_models.json').read_text(encoding='utf-8'))[name]
    if cache['status']!='available':raise RuntimeError('Model unavailable; no downloads')
    inputs=json.loads((out/'inputs.json').read_text(encoding='utf-8'))
    folder=out/'offline'/name
    def work(model,monitor):
        for sample in inputs:
            if digest(sample['file'])!=sample['sha256']:raise ValueError('Input changed')
            audio=np.frombuffer(read_wav(sample['file']),dtype='<i2').astype('float32')/32768.
            monitor.check();started=time.perf_counter()
            generator,info=model.transcribe(audio,**DECODE,initial_prompt=None,hotwords=None)
            segments=[asdict(s) for s in generator]
            elapsed=time.perf_counter()-started;monitor.check()
            text=''.join(s['text'] for s in segments)
            save(folder/(sample['id']+'.json'),{'model':name,'input':sample,'hypothesis_raw':text,
                'segments':segments,'asr_s':elapsed,'rtf':elapsed/sample['duration_s'],
                'language':info.language,'duration_after_vad':info.duration_after_vad,
                'options':{**DECODE,'initial_prompt':None,'hotwords':None},
                'reference_used_by_decoder':False,'clinical_wer':None})
            print(json.dumps({'model':name,'input':sample['id'],'text':text,'asr_s':elapsed}),flush=True)
    model_session(name,folder,cache,work)

def incremental(out,name,group):
    cache=json.loads((out/'cached_models.json').read_text(encoding='utf-8'))[name]
    folder=out/'incremental'/name/group
    def work(model,monitor):
        options={**DECODE,'initial_prompt':None,'hotwords':None,'vad_filter':True}
        from faster_whisper.vad import VadOptions
        from faster_whisper.utils import get_assets_path
        vad=Path(get_assets_path())/'silero_vad_v6.onnx'
        save(folder/'profile.json',{'model':name,'decoding':options,'config':asdict(Config(mode='adaptive')),
            'vad_sha256':digest(vad),'vad_options':{k:str(v) if isinstance(v,float) and not np.isfinite(v) else v for k,v in asdict(VadOptions()).items()},
            'engine':str(ROOT/'trad_lab/m4c/incremental.py'),'engine_sha256':digest(ROOT/'trad_lab/m4c/incremental.py'),
            'only_change_from_M4C_age1':'Model snapshot; no other algorithm or decode setting changes'})
        for sample in datasets(group):
            run_sample(model,sample,Config(mode='adaptive'),folder/sample['id'],monitor,options)
    model_session(name,folder,cache,work)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','cache','offline','incremental'])
    parser.add_argument('--out',required=True);parser.add_argument('--model',choices=MODELS)
    parser.add_argument('--group',choices=['full','yeti','clips'],default='full')
    args=parser.parse_args();out=Path(args.out)
    if args.action=='prepare':prepare(out);return
    dll=configure_runtime()
    if args.action=='cache':caches(out);return
    if not args.model:parser.error('--model required')
    try:
        if args.action=='offline':offline(out,args.model)
        else:incremental(out,args.model,args.group)
    except Exception as exc:
        save(out/(args.action+'_'+args.model+'_abort.json'),{'error_type':type(exc).__name__,'message':str(exc),'retry':False})
        raise

if __name__=='__main__':main()

"""Sequential GPU workers and local artifacts; no dependency installation or LIVE edits."""
from dataclasses import asdict
import datetime
import hashlib
import importlib.metadata
import inspect
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from .audio import corpus_pairs, decode, digest
from .metrics import NORMALIZATION, metrics, term_inventory
from .safety import LiveGuard, gpu_snapshot

MODEL_NAMES=('small','medium','large-v3-turbo')
DECODE={'language':'en','task':'transcribe','beam_size':5,'best_of':5,'temperature':0.,
        'condition_on_previous_text':True,'vad_filter':False,'word_timestamps':True}


def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def verify_completed(folder,inputs,model,context):
    """Reject partial or mismatched artifacts before reusing an expensive run."""
    folder=Path(folder)
    env=json.loads((folder/'environment.json').read_text(encoding='utf-8'))
    expected={**DECODE,'initial_prompt':env['decoding'].get('initial_prompt') if context else None,'hotwords':None}
    if (env['model']!=model or env.get('compute_type')!='float16' or env.get('device')!='cuda:0'
            or env['decoding']!=expected or bool(env['decoding']['initial_prompt'])!=context):
        raise ValueError('Completed model decoding profile changed')
    expected_ids={sample['id'] for sample in inputs}
    if {p.parent.name for p in folder.glob('*/result.json')}!=expected_ids:
        raise ValueError('Completed model sample set changed')
    for sample in inputs:
        path=folder/sample['id'];result=json.loads((path/'result.json').read_text(encoding='utf-8'))
        if (result['model']!=model or result['variant']!=('context' if context else 'baseline')
                or result['audio_sha256']!=sample['audio_sha256']
                or result['reference_sha256']!=sample['reference_sha256']
                or result['decoding']!=expected or result['reference_raw']!=sample['reference_raw']
                or result['hypothesis_raw']!=(path/'hypothesis.raw.txt').read_text(encoding='utf-8')
                or digest(path/'reference.original.txt')!=sample['reference_sha256']):
            raise ValueError('Completed model artifacts no longer match inputs/profile')


def environment():
    packages={}
    for name in ['faster-whisper','whisperlivekit','ctranslate2','torch','torchaudio','av','numpy','huggingface-hub']:
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:packages[name]=None
    return {'python':sys.version,'executable':sys.executable,'platform':platform.platform(),'packages':packages}


def model_worker(args):
    """Private subprocess entry: one model, reused sequentially for all samples."""
    out=Path(args.out)/'models'/(args.model+('-context' if args.context else ''))
    out.mkdir(parents=True,exist_ok=True)
    if (out/'status.json').exists():raise FileExistsError('Use a new output directory, never overwrite a model run')
    try:
        check=LiveGuard().check()
        if not check['safe']:raise RuntimeError('TRAD active or status unknown; no GPU load')
        from faster_whisper import WhisperModel
        from faster_whisper.utils import download_model
        import ctranslate2
        if 'float16' not in ctranslate2.get_supported_compute_types('cuda'):
            raise RuntimeError('float16 CUDA not supported; no fallback or package update')
        baseline_gpu=gpu_snapshot()
        planning_free={'small':1800,'medium':4000,'large-v3-turbo':6000}[args.model]
        if float(baseline_gpu['free_mib'])<planning_free:
            raise RuntimeError(f'Insufficient free VRAM for conservative planning reserve {planning_free} MiB')
        try: path=download_model(args.model,local_files_only=True)
        except Exception:
            if not args.allow_download:raise RuntimeError('Weights not cached; rerun with --allow-download (weights only)')
            path=download_model(args.model)
        path=Path(path)
        weights={str(p.relative_to(path)):{'bytes':p.stat().st_size,'sha256':digest(p)} for p in path.rglob('*') if p.is_file()}
        if not LiveGuard().check()['safe']:raise RuntimeError('TRAD became active before model load')
        started=time.perf_counter()
        model=WhisperModel(str(path),device='cuda',device_index=0,compute_type='float16',cpu_threads=4,num_workers=1)
        load_s=time.perf_counter()-started
        import numpy as np
        warm=time.perf_counter();segments,_=model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)
        list(segments);warmup_s=time.perf_counter()-warm
        prompt=None;prompt_terms=[]
        if args.context:
            document=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
            for term in document['terms']:
                candidate='; '.join([*prompt_terms,term['canonical']])
                if len(model.hf_tokenizer.encode(candidate).ids)>160 or len(prompt_terms)>=30:break
                prompt_terms.append(term['canonical'])
            prompt='; '.join(prompt_terms)
        options={**DECODE,'initial_prompt':prompt,'hotwords':None}
        defaults={k:p.default for k,p in inspect.signature(model.transcribe).parameters.items()
                  if p.default is not inspect.Parameter.empty and k not in options}
        env={**environment(),'gpu_before':baseline_gpu,'gpu_after_load':gpu_snapshot(),'model':args.model,
            'model_snapshot':str(path),'weight_manifest':weights,'compute_type':'float16','device':'cuda:0',
            'model_load_s':load_s,'warmup_s':warmup_s,'warmup':'0.5 s zeros, explicit English; excluded from timing',
            'decoding':options,'remaining_transcribe_defaults':defaults,'context_terms':prompt_terms,
            'context_selection':'first <=30 canonical terms in glossary order, <=160 tokenizer IDs; never selected from references'}
        save(out/'environment.json',env)
        inputs=json.loads((Path(args.out)/'inputs'/'inputs.json').read_text(encoding='utf-8'))
        for sample in inputs:
            if not LiveGuard().check()['safe']:raise RuntimeError('TRAD became active; aborting own benchmark')
            before=time.perf_counter();audio=decode(sample['audio_path']);decode_s=time.perf_counter()-before
            audio_hash=hashlib.sha256(audio.astype('<f4').tobytes()).hexdigest()
            if audio_hash!=sample['audio']['float32_sha256']:raise RuntimeError('Decoded audio changed')
            before=time.perf_counter()
            generated,info=model.transcribe(audio,**options)
            segments=[asdict(s) for s in generated]
            asr_s=time.perf_counter()-before
            text=''.join(s['text'] for s in segments)
            duration=len(audio)/16000
            result={'status':'completed','sample_id':sample['id'],'model':args.model,
                'variant':'context' if args.context else 'baseline','audio_sha256':sample['audio_sha256'],
                'reference_sha256':sample['reference_sha256'],'reference_status':sample['reference_status'],
                'reference_raw':sample['reference_raw'],'hypothesis_raw':text,'audio':sample['audio'],
                'decode_s':decode_s,'asr_wall_s':asr_s,'audio_duration_s':duration,'rtf':asr_s/duration,
                'timing_policy':'generator fully consumed; model load/warmup, MP3 decode, metrics and reports excluded from ASR RTF',
                'normalization':NORMALIZATION,'metrics':metrics(sample['reference_raw'],text),
                'segments':segments,'asr_info':{k:getattr(info,k,None) for k in ['language','language_probability','duration','duration_after_vad']},
                'asr_info_caution':'language=en is forced; probability is not a measured language-detection or clinical confidence',
                'gpu_at_sample_end':gpu_snapshot(),'decoding':options}
            folder=out/sample['id'];folder.mkdir()
            (folder/'hypothesis.raw.txt').write_text(text,encoding='utf-8')
            (folder/'reference.original.txt').write_bytes(Path(sample['reference_path']).read_bytes())
            save(folder/'result.json',result)
            print(json.dumps({'model':args.model,'variant':result['variant'],'sample':sample['id'],
                'wer':result['metrics']['wer'],'cer':result['metrics']['cer'],'rtf':result['rtf']},ensure_ascii=True),flush=True)
        save(out/'status.json',{'status':'completed','model':args.model,'samples':len(inputs)})
    except Exception as exc:
        save(out/'status.json',{'status':'blocked','model':args.model,'error_type':type(exc).__name__,'reason':str(exc)})
        print(f'BLOCKED {args.model}: {type(exc).__name__}: {exc}',flush=True)
        return 2
    return 0


def evaluate(args):
    """Parent monitors LIVE and aggregate GPU memory; only own worker is stopped."""
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    exists=(out/'experiment.json').exists()
    if exists and not args.resume:raise FileExistsError('Choose a new output directory, or explicitly --resume identical inputs/profile')
    from .audio import prepare
    from .glossary import audit
    if exists:
        previous=json.loads((out/'experiment.json').read_text(encoding='utf-8'))
        inputs=json.loads((out/'inputs/inputs.json').read_text(encoding='utf-8'))
        if 'corpus' in previous and Path(previous['corpus']).resolve()!=Path(args.corpus).resolve():
            raise ValueError('Resume corpus directory changed')
        if previous['decoding']!=DECODE or previous['glossary_sha256']!=digest(args.glossary) or previous['models']!=args.models:
            raise ValueError('Resume profile/glossary/model list changed')
        for sample in inputs:
            if digest(sample['audio_path'])!=sample['audio_sha256'] or digest(sample['reference_path'])!=sample['reference_sha256']:
                raise ValueError('Original corpus changed; do not mix runs')
    else:inputs=prepare(args.corpus,out/'inputs')
    audit_result=audit(args.glossary);save(out/'glossary_audit.json',audit_result)
    if not exists:save(out/'experiment.json',{'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'corpus':str(Path(args.corpus).resolve()),'models':args.models,'environment':environment(),
        'decoding':DECODE,'normalization':NORMALIZATION,'glossary_sha256':audit_result['sha256'],
        'weights_download_allowed':args.allow_download,'services_started':False,'deepl_calls':0,
        'outputs_private_local':True,'reference_status':inputs[0]['reference_status']})
    variants=[(name,False) for name in args.models]
    if args.with_context:variants.append(('small',True))
    small_completed=False
    for model,context in variants:
        folder=out/'models'/(model+('-context' if context else ''))
        if args.resume and folder.exists():
            old=json.loads((folder/'status.json').read_text(encoding='utf-8')) if (folder/'status.json').exists() else {}
            if old.get('status')=='completed':
                verify_completed(folder,inputs,model,context)
                if model=='small' and not context:small_completed=True
                print(json.dumps({'model':model,'context':context,'status':'reused_verified_inputs'}),flush=True)
                continue
            # Preserve an interrupted/blocked attempt; never delete its evidence.
            if folder.is_symlink() or not folder.resolve().is_relative_to(out/'models'):
                raise ValueError('Unsafe attempt archive path')
            archive=out/'attempts'/(folder.name+'-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            archive.parent.mkdir(exist_ok=True);shutil.move(str(folder),str(archive))
        if model!='small' and not small_completed:
            save(folder/'status.json',{'status':'blocked','reason':'small baseline must finish successfully first'})
            continue
        guard=LiveGuard();check=guard.check()
        if not check['safe']:
            save(folder/'status.json',{'status':'blocked','reason':'LIVE guard','state':check});continue
        cmd=[sys.executable,'-m','trad_lab','_worker','--model',model,'--out',str(out),'--glossary',args.glossary]
        if args.allow_download:cmd.append('--allow-download')
        if context:cmd.append('--context')
        env=os.environ.copy();env['PYTHONIOENCODING']='utf-8';env['OMP_NUM_THREADS']='4'
        lib=Path(sys.executable).resolve().parents[1]/'Lib/site-packages/torch/lib'
        env['PATH']=str(lib)+os.pathsep+env.get('PATH','')
        folder.mkdir(parents=True,exist_ok=True)
        samples=[];aborted=None
        with (folder/'worker.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            started=time.monotonic()
            try:
                while process.poll() is None:
                    state=guard.check()
                    if not state['safe'] or time.monotonic()-started>args.model_timeout_seconds:
                        aborted=state if not state['safe'] else {'reason':'model_worker_wall_time_limit'}
                        process.terminate();process.wait(timeout=15);break
                    try:samples.append({'time_mono':time.monotonic(),**gpu_snapshot()})
                    except Exception:pass
                    time.sleep(2)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=15)
        save(folder/'gpu_samples.json',{'sampling_seconds':2,'samples':samples,
            'measurement':'NVIDIA-SMI total device VRAM; includes Windows/other processes; not exact per-process CT2 allocator peak',
            'peak_used_mib':max((float(s['used_mib']) for s in samples),default=None),
            'baseline_used_mib':float(samples[0]['used_mib']) if samples else None})
        if aborted:
            save(folder/'status.json',{'status':'blocked','reason':'Own worker stopped by LIVE or wall-time guard','guard':aborted})
        elif not (folder/'status.json').exists():
            save(folder/'status.json',{'status':'blocked','reason':'Worker exited without completion','exit_code':process.returncode})
        status=json.loads((folder/'status.json').read_text(encoding='utf-8'))
        if model=='small' and not context:small_completed=status['status']=='completed'
        print(json.dumps({'model':model,'context':context,'status':status['status']},ensure_ascii=True),flush=True)
    from .report import reports
    reports(out,args.glossary)
    statuses=[json.loads((out/'models'/(name+('-context' if context else ''))/'status.json').read_text(encoding='utf-8')) for name,context in variants]
    return 0 if all(s['status']=='completed' for s in statuses) else 2

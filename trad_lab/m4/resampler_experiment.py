"""Synthetic upsample -> actual worker / phase-carry prototype -> fixed ASR.

Full accepted fragment content is preserved. This omits browser fake-source
start, AGC, microphone and network; clinical acceptance does not follow from it.
"""
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import time
import wave

from trad_lab.audio import digest
from trad_lab.runner import DECODE,save,environment
from .audio_analysis import read_pcm
from .experiments import load_samples,cached_models,Monitor,score


def run(args):
    import numpy as np
    from scipy.signal import resample_poly
    from faster_whisper import WhisperModel
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    samples=load_samples(args.clips);glossary=json.loads(Path(args.glossary).read_text(encoding='utf-8-sig'))
    derived=[]
    for sample in samples:
        folder=out/sample['id'];folder.mkdir()
        parent=read_pcm(sample['wav_path'])
        path=folder/'common_48k.f32';resample_poly(parent,3,1).astype('<f4').tofile(path)
        result=subprocess.run(['C:/Program Files/nodejs/node.exe',str(Path(__file__).with_name('resampler_pair.cjs')),str(path),str(folder/'output')],capture_output=True,text=True,check=True)
        data=json.loads(result.stdout);save(folder/'worker_pair.json',data)
        for profile in ['production','phase_carry']:
            pcm=(folder/('output.'+profile+'.s16')).read_bytes();wav=folder/(profile+'.wav')
            with wave.open(str(wav),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(pcm)
            derived.append((sample,profile,wav))
    with Monitor(out/'gpu_samples.jsonl') as monitor:
        encoder,_=cached_models();model=WhisperModel(str(encoder),device='cuda',compute_type='float16',cpu_threads=4,num_workers=1)
        list(model.transcribe(np.zeros(8000,dtype='float32'),**DECODE)[0])
        save(out/'environment.json',{**environment(),'only_varied':'sample phase continuity in resample(); same synthetic 48 kHz signal, 128-sample blocks, converter, FW small float16 beam5',
            'limitations':'Synthetic full-content waveform transform, not the browser/microphone path; source reference acceptance and boundary uncertainty inherited, not a new human review',
            'decoding':{**DECODE,'initial_prompt':None,'hotwords':None}})
        for repeat in range(args.repeats):
            for sample,profile,wav in (derived if repeat%2==0 else reversed(derived)):
                monitor.check();audio=read_pcm(wav).astype('float32');before=time.perf_counter()
                generated,_=model.transcribe(audio,**DECODE,initial_prompt=None,hotwords=None)
                segments=[asdict(s) for s in generated];wall=time.perf_counter()-before;text=''.join(s['text'] for s in segments)
                result={'sample':sample['id'],'family':'synthetic_resampler','profile':profile,'repeat':repeat,
                    'wav_path':str(wav.resolve()),'wav_sha256':digest(wav),'parent_wav_sha256':sample['wav_sha256'],
                    'reference_inheritance':'Same complete accepted fragment content; only controlled resampling transform',
                    'hypothesis_raw':text,'segments':segments,'audio_s':len(audio)/16000,'asr_wall_s':wall,'rtf':wall/(len(audio)/16000),**score(sample,text,glossary)}
                save(out/f"{sample['id']}.{profile}.r{repeat}.json",result)
                print(json.dumps({'sample':sample['id'],'profile':profile,'repeat':repeat,'wer':result['accuracy']['wer'] if result['accuracy'] else None}),flush=True)
        monitor.check()
    save(out/'gpu_samples.json',{'samples':monitor.samples})

"""Timing evidence from saved PCM; no microphone, server or model download."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import wave

from trad_lab.audio import digest
from trad_lab.runner import save


def read_pcm(path):
    import numpy as np
    with wave.open(str(path),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):
            raise ValueError('Expected mono s16 16000 Hz WAV')
        return np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype('float64')/32768


def best_match(template,recording):
    import numpy as np
    from scipy.signal import fftconvolve
    template=template-template.mean();n=len(template)
    if n>len(recording) or not np.linalg.norm(template):raise ValueError('Invalid alignment window')
    sums=np.r_[0.,np.cumsum(recording)];squares=np.r_[0.,np.cumsum(recording**2)]
    variance=np.maximum(0.,squares[n:]-squares[:-n]-(sums[n:]-sums[:-n])**2/n)
    dots=fftconvolve(recording,template[::-1],mode='valid')
    corr=dots/np.maximum(1e-12,np.sqrt(variance*np.sum(template**2)))
    index=int(np.argmax(np.abs(corr)))
    return index,float(corr[index])


def align(source,captured,ratio):
    import numpy as np
    from scipy.signal import resample_poly
    from fractions import Fraction
    fraction=Fraction(ratio).limit_denominator(10000);rows=[]
    # Independent windows reveal drift; no transcript alignment is used here.
    for start in range(0,max(1,int(len(source)/16000)-5),10):
        original=source[start*16000:(start+5)*16000]
        if len(original)!=80000:continue
        template=resample_poly(original,fraction.numerator,fraction.denominator)
        offset,correlation=best_match(template,captured)
        rows.append({'source_start_s':start,'capture_start_s':offset/16000,'correlation':correlation})
    good=[r for r in rows if abs(r['correlation'])>=.55]
    fit=None
    if len(good)>=3:
        slope,intercept=np.polyfit([r['source_start_s'] for r in good],[r['capture_start_s'] for r in good],1)
        errors=[r['capture_start_s']-(slope*r['source_start_s']+intercept) for r in good]
        fit={'slope':float(slope),'intercept_s':float(intercept),'max_anchor_residual_s':float(max(abs(x) for x in errors)),
            'estimated_missing_source_prefix_s':float(max(0.,-intercept/slope)),
            'estimated_capture_tail_after_source_end_s':float(len(captured)/16000-(slope*len(source)/16000+intercept))}
    return {'template_time_scale':float(fraction),'anchors':rows,'reliable_anchor_count':len(good),'affine_fit':fit,
        'method':'5 s waveform templates, FFT normalized correlation; >=0.55 threshold is an engineering review heuristic, not clinical validation'}


def worker_probe(out):
    node=Path('C:/Program Files/nodejs/node.exe')
    if not node.exists():raise RuntimeError('Existing Node runtime missing; no install allowed')
    script=Path(__file__).with_name('worker_probe.cjs')
    result=subprocess.run([str(node),str(script)],capture_output=True,text=True,check=True)
    data=json.loads(result.stdout);save(Path(out)/'actual_worker_probe.json',data)
    return data


def analyze(source_path,captured_path,out):
    import numpy as np
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    source,captured=read_pcm(source_path),read_pcm(captured_path)
    def stats(a):
        windows=[float(np.sqrt(np.mean(a[i:i+1600]**2))) for i in range(0,len(a),1600)]
        return {'samples':len(a),'duration_s':len(a)/16000,'rms':float(np.sqrt(np.mean(a*a))),
            'peak':float(np.max(np.abs(a))),'zero_fraction':float(np.mean(a==0)),
            'rms_100ms':windows,'near_silence_threshold':1e-4,
            'near_silence_intervals_s':[[i/10,(i+1)/10] for i,v in enumerate(windows) if v<1e-4]}
    result={'source':{'path':str(Path(source_path).resolve()),'sha256':digest(source_path),**stats(source)},
        'captured':{'path':str(Path(captured_path).resolve()),'sha256':digest(captured_path),**stats(captured)},
        'alignments':[align(source,captured,1.),align(source,captured,129/128)],
        'actual_worker':worker_probe(out),
        'limits':'Waveform evidence only. Browser fake-file start, AGC, resampling and queue timing differ from a real microphone. Correlation cannot certify clinical words or rule out every duplication.'}
    save(out/'audio_diagnostic.json',result)
    return result

"""CPU waveform anchors between the original MP3 and browser mono input.

Signed, gain/DC-invariant correlations are evidence, not a defect verdict.
Sparse anchors cannot prove completeness or certify transcript boundaries.
"""
import json
import math
from pathlib import Path


def align(capture):
    import numpy as np
    from scipy.signal import resample_poly
    from trad_lab.audio import decode, digest, write_wav
    from trad_lab.m4.audio_analysis import best_match
    capture=Path(capture).resolve();analysis=json.loads((capture/'analysis.json').read_text(encoding='utf-8'))
    source=Path('C:/TRAD-LAB/corpus/cardio_01/audio.mp3')
    if digest(source)!='59d1ec58514134f7bf326d824e33f61eb868713b71cad147395563104119a25d':raise ValueError('Original MP3 changed')
    if not any(r.get('valid') for r in analysis['source_playback'] if r['kind']=='reference_file'):raise ValueError('Playback source not verified')
    audio=decode(source)[:16000*100];pre=np.fromfile(capture/'browser/pre.f32le',dtype='<f4')
    rate=analysis['integrity']['rate'];gcd=math.gcd(rate,16000)
    standard=resample_poly(pre,16000//gcd,rate//gcd) if rate!=16000 else pre
    anchors=[]
    for sec in (0,10,30,50,70,90):
        template=audio[int(sec*16000):int((sec+4)*16000)]
        index,corr=best_match(template,standard)
        anchors.append({'source_s':sec,'captured_s':index/16000,'signed_correlation':corr,'duration_s':4})
    reliable=[a for a in anchors if abs(a['signed_correlation'])>=.5]
    fit=None
    if len(reliable)>=3:
        x=np.array([a['source_s'] for a in reliable]);y=np.array([a['captured_s'] for a in reliable])
        slope,offset=np.polyfit(x,y,1)
        fit={'slope':float(slope),'offset_s':float(offset),'max_residual_s':float(np.max(np.abs(y-(slope*x+offset)))),
             'selected_anchors':len(reliable),'selection_rule':'abs(correlation)>=0.5, descriptive screening only'}
    clip=capture/'source_0_100s.wav'
    if clip.exists():raise FileExistsError('Source derivative already exists')
    write_wav(clip,audio)
    result={'source_mp3_sha256':digest(source),'pre_f32_sha256':digest(capture/'browser/pre.f32le'),
        'anchors':anchors,'fit':fit,'source_wav_sha256':digest(clip),
        'scope':'Original decoded MP3 vs same physical mono capture; SciPy resample_poly only for analysis',
        'caution':'Low correlations are inconclusive. Sparse anchors do not prove no dropped speech or exact TXT bounds; inspect first/last phrases and adjudicate clinically.'}
    with (capture/'alignment.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    return result

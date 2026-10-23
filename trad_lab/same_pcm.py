"""Offline replay of the exact PCM observed at authenticated CAPTURE transport."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .audio import decode,describe,digest
from .metrics import metrics,tokens
from .runner import DECODE,evaluate,save


def compare(args):
    capture=Path(args.capture).resolve();out=Path(args.out).resolve()
    if out.exists():raise FileExistsError('Choose a new diagnostic output directory')
    out.mkdir(parents=True)
    reference=out/'no_reviewed_fragment_reference.txt';reference.write_text('',encoding='utf-8')
    pairs=[]
    for name,path in [('source_clip',Path(args.source).resolve()),('sent_pcm',capture/'capture.sent_pcm.wav')]:
        audio=decode(path)
        pairs.append({'id':name,'audio_path':str(path),'audio_sha256':digest(path),
            'reference_path':str(reference),'reference_sha256':digest(reference),'reference_raw':'',
            'reference_status':'No matching reviewed reference for this diagnostic cut; WER/CER accuracy undefined',
            'audio':describe(path,audio)})
    save(out/'inputs/inputs.json',pairs)
    save(out/'experiment.json',{'models':['small'],'decoding':DECODE,'glossary_sha256':digest(args.glossary),
        'purpose':'Same-PCM hypothesis disagreement, not clinical accuracy ranking','reference_status':pairs[0]['reference_status']})
    evaluate(SimpleNamespace(out=str(out),corpus=str(out),models=['small'],glossary=args.glossary,
        allow_download=False,with_context=False,resume=True,model_timeout_seconds=600))
    modeldir=out/'models/small'
    if json.loads((modeldir/'status.json').read_text())['status']!='completed':return 2
    source=json.loads((modeldir/'source_clip/result.json').read_text(encoding='utf-8'))['hypothesis_raw']
    sent=json.loads((modeldir/'sent_pcm/result.json').read_text(encoding='utf-8'))['hypothesis_raw']
    stream=json.loads((capture/'streaming_comparison.json').read_text(encoding='utf-8'))
    raw,ready=stream['raw_before_segment_manager'],stream['ready_after_segment_manager']
    result={'scope':'Normalized hypothesis disagreement, never accuracy WER without a matching reviewed reference',
        'source_clip_offline':source,'captured_pcm_offline':sent,'wlk_raw':raw,'trad_ready':ready,
        'offline_source_vs_offline_capture':metrics(source,sent),
        'offline_capture_vs_wlk_raw':metrics(sent,raw),'wlk_raw_vs_trad_ready':metrics(raw,ready),
        'normalized_raw_ready_equal':tokens(raw)==tokens(ready),'wlk_decoder_evidence':stream['config']['wlk'].get('lab_decoder_evidence'),
        'source_wav_sha256':digest(args.source),'captured_wav_sha256':digest(capture/'capture.sent_pcm.wav'),
        'limits':'Different hypotheses locate a pipeline stage, not necessarily its root cause or clinical correctness. Browser timing and PCM length must be reviewed.'}
    save(out/'differential.json',result)
    text='# Same-PCM differential\n\nNo matching reviewed cut reference: the following are hypothesis disagreement ratios, not clinical WER.\n\n'
    for label,key in [('Offline original clip → offline captured PCM','offline_source_vs_offline_capture'),('Offline captured PCM → WLK RAW','offline_capture_vs_wlk_raw'),('WLK RAW → actual TRAD READY','wlk_raw_vs_trad_ready')]:
        m=result[key];value='undefined' if m['wer'] is None else f"{m['wer']:.2%}"
        text+=f'- {label}: {value}, S/D/I {m["substitutions"]}/{m["deletions"]}/{m["insertions"]}.\n'
    text+='\nActual WLK decoder evidence:\n\n```json\n'+json.dumps(result['wlk_decoder_evidence'],indent=2)+'\n```\n'
    text+='\nReview raw texts in differential.json and transport hashes/durations in capture.json before attributing causes. No DeepL, no live configuration changes.\n'
    (out/'DIFFERENTIAL.md').write_text(text,encoding='utf-8')
    return 0

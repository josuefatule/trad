"""Summarize completed M4 artifacts, excluding all truncated decoder attempts."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import statistics

from trad_lab.metrics import metrics,tokens
from trad_lab.runner import save


def format_equivalence(text):
    # Secondary, post-hoc diagnostic only. Primary scoring remains untouched.
    text=re.sub(r'(\d+(?:[.,]\d+)?)\s*%',r'\1 percent',text)
    text=re.sub(r'\bstage\s+(one|two)\b',lambda m:'stage '+{'one':'1','two':'2'}[m[1].lower()],text,flags=re.I)
    return text


def summarize(root):
    root=Path(root);rows=[];groups=defaultdict(list)
    for folder in ['offline','resampler_pair','local_agreement']:
        if not (root/folder).exists():continue
        gpu_path=root/folder/'gpu_samples.jsonl'
        if gpu_path.exists():gpu=[json.loads(s) for s in gpu_path.read_text().splitlines()]
        elif (root/folder/'gpu_samples.json').exists():gpu=json.loads((root/folder/'gpu_samples.json').read_text())['samples']
        else:gpu=[]
        for path in sorted((root/folder).glob('*.json')):
            d=json.loads(path.read_text(encoding='utf-8'))
            if 'hypothesis_raw' not in d:continue
            m=d.get('accuracy');profile=str(d.get('beam',d.get('profile','')))
            secondary=metrics(format_equivalence(Path(next(s['reference_path'] for s in json.loads((root/'references/clips.json').read_text()) if s['id']==d['sample'])).read_text(encoding='utf-8')),format_equivalence(d['hypothesis_raw'])) if m else None
            row={'family':d['family'],'profile':profile,'sample':d['sample'],'repeat':d['repeat'],
                'path':str(path.resolve()),'wer':m['wer'] if m else None,'cer':m['cer'] if m else None,
                'word_errors':m['word_errors'] if m else None,'reference_words':m['reference_words'] if m else None,
                'character_errors':m['character_errors'] if m else None,'reference_characters':m['reference_characters'] if m else None,
                'secondary_format_review_word_errors':secondary['word_errors'] if secondary else None,
                'secondary_format_review_reference_words':secondary['reference_words'] if secondary else None,
                'risk_flags':m['risk_flag_counts'] if m else {},'term_deficit':sum(t['occurrence_deficit'] for t in d.get('term_inventory') or []),
                'asr_wall_s':d['asr_wall_s'],'audio_s':d['audio_s'],'rtf':d['rtf'],
                'raw_sha256':hashlib.sha256(d['hypothesis_raw'].encode()).hexdigest(),
                'normalized_sha256':hashlib.sha256(' '.join(tokens(d['hypothesis_raw'])).encode()).hexdigest(),
                'commit_lag_median_s':d.get('commit_lag_median_s'),'commit_lag_max_s':d.get('commit_lag_max_s'),
                'eof_unconfirmed_tail_words':len(d.get('eof_unconfirmed_tail',[])),
                'gpu_total_peak_mib':max((float(s['used_mib']) for s in gpu),default=None),
                'gpu_util_mean':statistics.mean(float(s['util_percent']) for s in gpu) if gpu else None,
                'gpu_sample_actual_median_gap_s':statistics.median(b['at']-a['at'] for a,b in zip(gpu,gpu[1:])) if len(gpu)>1 else None}
            rows.append(row);groups[(row['family'],profile)].append(row)
    aggregate=[]
    for (family,profile),values in groups.items():
        words=sum(r['reference_words'] or 0 for r in values);chars=sum(r['reference_characters'] or 0 for r in values)
        secondary_words=sum(r['secondary_format_review_reference_words'] or 0 for r in values)
        per_sample=defaultdict(list)
        for r in values:per_sample[r['sample']].append(r)
        aggregate.append({'family':family,'profile':profile,'inferences':len(values),'samples':len(per_sample),
            'accuracy_inferences':sum(r['wer'] is not None for r in values),
            'pooled_wer':sum(r['word_errors'] or 0 for r in values)/words if words else None,
            'pooled_cer':sum(r['character_errors'] or 0 for r in values)/chars if chars else None,
            'secondary_format_review_wer':sum(r['secondary_format_review_word_errors'] or 0 for r in values)/secondary_words if secondary_words else None,
            'rtf':sum(r['asr_wall_s'] for r in values)/sum(r['audio_s'] for r in values),
            'repeat_distinct_normalized_hypotheses':{sample:len({v['normalized_sha256'] for v in group}) for sample,group in per_sample.items()},
            'gpu_total_peak_mib':values[0]['gpu_total_peak_mib'],'gpu_util_mean':values[0]['gpu_util_mean']})
    result={'rows':rows,'aggregate':aggregate,'primary_reference_status':'User accepted using the three reviewed MP3 samples; derived temporal WAV/TXT references retain 0.58/0.70/1.37 s boundary spread and are not certified ground truth',
        'secondary_policy':'Post-hoc explanatory sensitivity: % -> percent and stage one/two -> stage 1/2, symmetrically. Not an acceptance metric or a clinical equivalence engine.',
        'blocked_attempts':[{**json.loads((root/f/'status.json').read_text()),'folder':f} for f in ['simul','simul_sync','pipeline'] if (root/f/'status.json').exists()],
        'live_promoted':False,'visible_latency':'No new browser/OBS measurement without separately authorized services'}
    save(root/'comparison.json',result)
    md='# M4 — completed isolated experiments\n\nProvisional temporal references. Truncated AlignAtt attempts excluded. No candidate approved.\n\n| Family | Profile | Sample | Repeat | WER | CER | RTF | Term deficit proxy |\n|---|---|---|---:|---:|---:|---:|---:|\n'
    pct=lambda v:'pending reference' if v is None else f'{v:.2%}'
    for r in rows:md+=f"| {r['family']} | {r['profile']} | {r['sample']} | {r['repeat']} | {pct(r['wer'])} | {pct(r['cer'])} | {r['rtf']:.4f} | {r['term_deficit']} |\n"
    md+='\n## Aggregate\n\n| Family | Profile | n | WER | CER | RTF | Secondary format sensitivity WER |\n|---|---|---:|---:|---:|---:|---:|\n'
    for r in aggregate:md+=f"| {r['family']} | {r['profile']} | {r['inferences']} | {pct(r['pooled_wer'])} | {pct(r['pooled_cer'])} | {r['rtf']:.4f} | {pct(r['secondary_format_review_wer'])} |\n"
    md+='\nSecondary scoring is post-hoc and explanatory only. References, raw hypotheses and primary WER/CER remain unchanged. Offline RTF, algorithmic commit lag and visible latency have different clocks and must not be equated.\n'
    (root/'COMPARISON.md').write_text(md,encoding='utf-8')
    return result

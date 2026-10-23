"""Read-only replay of saved ASR outputs through the actual soft integration."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time

from app.captions.identity_normalizer import IdentityNormalizer
from app.terminology.rollout import GlossaryConfig, session_normalizer
from trad_lab.metrics import edit_distance, tokens

ROOT=Path(__file__).resolve().parents[1]
RESEARCH=ROOT/'research/hypertension_2026-10-20/polarity_flexible_trial_97_v1'
OUT=ROOT/'benchmarks/glossary_soft_v1'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    normalizer=session_normalizer(GlossaryConfig(state_path=''),'en',IdentityNormalizer())
    controls=[]
    for filename in ['existing_regression_cases.json','pressure_cases.json']:
        cases=read(RESEARCH/filename)
        rows=[]
        for case in cases:
            result=normalizer.normalize(case['case_id'],case['text'])
            rows.append(dict(case_id=case['case_id'],kind=case['kind'],positive=case['positive'],
                input=case['text'],expected=case['expected'],actual=result.normalized_text,
                exact_expected=result.normalized_text==case['expected'],
                changed=result.normalized_text!=case['text'],latency_ms=result.processing_ms))
        controls.append(dict(source=filename,total=len(rows),
            negative_cases=sum(not r['positive'] for r in rows),
            negative_rewrites=sum(not r['positive'] and r['changed'] for r in rows),
            expected_matches=sum(r['exact_expected'] for r in rows),rows=rows))
        print(filename,controls[-1]['expected_matches'],'/',len(rows),flush=True)
    previous=read(RESEARCH/'visible_root_refinement_v2/speech_comparison.json')['aggregate']
    aggregates=[];samples=[]
    for model in ['small','medium','large-v3-turbo']:
        group=[]
        for sample in ['cardio_01','cardio_02','cardio_03']:
            path=ROOT/'logs/trad_lab/20261020T074247Z/evaluation/models'/model/sample/'result.json'
            data=read(path);ref=tokens(data['reference_raw']);raw=data['hypothesis_raw']
            start=time.perf_counter();result=normalizer.normalize(sample,raw)
            elapsed=(time.perf_counter()-start)*1000
            row=dict(model=model,sample=sample,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                reference_words=len(ref),raw_word_errors=edit_distance(ref,tokens(raw)),
                soft_word_errors=edit_distance(ref,tokens(result.normalized_text)),
                correction_count=len(result.corrections),normalization_ms=elapsed,
                corrections=[asdict(c) for c in result.corrections],output=result.normalized_text)
            group.append(row);samples.append(row)
            print(model,sample,row['raw_word_errors'],row['soft_word_errors'],round(elapsed),'ms',flush=True)
        old=next(r for r in previous if r['model']==model and r['profile']=='direction_guard_same')
        words=sum(r['reference_words'] for r in group)
        aggregates.append(dict(model=model,reference_words=words,
            raw_word_errors=sum(r['raw_word_errors'] for r in group),
            prior_laboratory_word_errors=old['word_errors'],
            soft_word_errors=sum(r['soft_word_errors'] for r in group),
            soft_wer=sum(r['soft_word_errors'] for r in group)/words,
            corrections=sum(r['correction_count'] for r in group)))
    snippets=['No primary allosteronism by this test; keep ≥5 mg.',
        'They discussed orthostatic hypotension and physical inactivity.',
        'Resistant hypertension requires careful monitoring of blood pressure.']
    latency=[]
    for i in range(30):
        result=normalizer.normalize(str(i),snippets[i%len(snippets)])
        latency.append(result.processing_ms)
    report=dict(generated_utc=datetime.now(timezone.utc).isoformat(),version=normalizer.release.version,
        scope='Saved ASR text replay only; provisional reference, not a new recording or live provider evaluation.',
        aggregate=aggregates,controls=controls,samples=samples,
        short_segment_latency_ms=dict(n=len(latency),median=statistics.median(latency),p95=sorted(latency)[28],max=max(latency)))
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'replay_results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert all(c['negative_rewrites']==0 for c in controls),'Negative control rewrite: inspect report'
    assert all(a['soft_word_errors']<=a['prior_laboratory_word_errors'] for a in aggregates),'WER regression: inspect report'
    print('PASS: no negative control rewrites and no replay WER regression',flush=True)

if __name__=='__main__':main()

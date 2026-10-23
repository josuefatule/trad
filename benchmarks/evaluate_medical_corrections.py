"""Paired text-only validation of the bounded MVP patch against streaming v2."""
from collections import Counter
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics

from app.captions.identity_normalizer import IdentityNormalizer
from app.terminology.rollout import GlossaryConfig,session_normalizer
from trad_lab.metrics import edit_distance,tokens

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmarks/glossary_patch_v1'
RESEARCH=ROOT/'research/hypertension_2026-10-20/polarity_flexible_trial_97_v1'


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    base=session_normalizer(GlossaryConfig(patch_enabled=False,state_path=''),'en',IdentityNormalizer())
    new=session_normalizer(GlossaryConfig(state_path=''),'en',IdentityNormalizer())
    readings=[]
    for path in [ROOT/'benchmarks/glossary_soft_v2/first_reading.json',OUT/'second_reading.json']:
        snapshot=read(path);rows=[]
        for event in snapshot['operator_history']['events']:
            message=event['message']
            if message['type']!='segmentation':continue
            for segment in message['normalization']['segments']:
                a=base.normalize(segment['segment_id'],segment['raw_text'])
                b=new.normalize(segment['segment_id'],segment['raw_text'])
                rows.append(dict(segment_id=segment['segment_id'],raw=segment['raw_text'],
                    observed_normalized=segment['normalized_text'],streaming_v2=a.normalized_text,patched=b.normalized_text,
                    corrections=[asdict(c) for c in b.corrections],suggestions=[asdict(s) for s in b.suggestions],
                    terminology_context=new.translation_context(b.normalized_text,'en','es')))
        readings.append(dict(source=path.relative_to(ROOT).as_posix(),segments=len(rows),
            changed_vs_v2=sum(r['streaming_v2']!=r['patched'] for r in rows),
            review_only=sum(s['rule']=='medical_context_review_only' for r in rows for s in r['suggestions']),rows=rows))
    assert readings[0]['changed_vs_v2']==0
    assert readings[1]['changed_vs_v2']==1 and readings[1]['review_only']==1
    controls=[]
    for filename in ['existing_regression_cases.json','pressure_cases.json']:
        rows=[]
        for case in read(RESEARCH/filename):
            output=new.normalize(case['case_id'],case['text']).normalized_text
            rows.append(dict(**case,actual=output,passed=output==case['expected']))
        controls.append(dict(source=filename,total=len(rows),expected_matches=sum(r['passed'] for r in rows),
            negative_rewrites=sum(not r['positive'] and r['actual']!=r['text'] for r in rows),rows=rows))
    assert all(r['negative_rewrites']==0 for r in controls)
    print('Reading comparison and 250 inherited controls passed',flush=True)
    samples=[];aggregate=[]
    for model in ['small','medium','large-v3-turbo']:
        group=[]
        for sample in ['cardio_01','cardio_02','cardio_03']:
            path=ROOT/'logs/trad_lab/20261020T074247Z/evaluation/models'/model/sample/'result.json'
            data=read(path);raw=data['hypothesis_raw'];reference=tokens(data['reference_raw'])
            a=base.normalize(sample,raw);b=new.normalize(sample,raw)
            row=dict(model=model,sample=sample,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                reference_words=len(reference),streaming_v2_word_errors=edit_distance(reference,tokens(a.normalized_text)),
                patch_word_errors=edit_distance(reference,tokens(b.normalized_text)),
                streaming_v2_changes=len(a.corrections),patch_changes=len(b.corrections),
                additional_spelling_repairs=sum(c.rule=='medical_observed_spelling' for c in b.corrections),
                patched_output=b.normalized_text)
            group.append(row);samples.append(row)
            print(json.dumps(dict(model=model,sample=sample,before=row['streaming_v2_word_errors'],after=row['patch_word_errors'])),flush=True)
        aggregate.append(dict(model=model,reference_words=sum(r['reference_words'] for r in group),
            streaming_v2_word_errors=sum(r['streaming_v2_word_errors'] for r in group),
            patch_word_errors=sum(r['patch_word_errors'] for r in group)))
    snippets=['No primary adosterizm by this test; keep 5 mg, not 50 mg.',
        'The patient has resisted hyper tension and chronic kidney disease.',
        'White coat hypertension and non elevated blood pressure.']
    timings=[]
    for i in range(30):timings.append(new.normalize(str(i),snippets[i%3]).processing_ms)
    audit=read(OUT/'catalog_audit.json')
    report=dict(generated_utc=datetime.now(timezone.utc).isoformat(),patch=new.patch.status(),
        scope='Paired saved text replay, not new ASR inference or real provider/OBS evaluation; provisional references.',
        readings=readings,controls=controls,aggregate=aggregate,samples=samples,
        catalog=dict(concepts=audit['concept_count'],language_forms=dict(Counter(r['language'] for r in audit['format_recognition'])),
            unique_format_concepts=len({r['concept_id'] for r in audit['format_recognition']}),
            collisions=audit['lexical_collisions']),
        short_segment_latency_ms=dict(n=len(timings),median=statistics.median(timings),p95=sorted(timings)[28],max=max(timings)))
    (OUT/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert all(a['patch_word_errors']<=a['streaming_v2_word_errors'] for a in aggregate)
    print('PASS: no inherited negative rewrite and no saved-ASR WER regression',flush=True)


if __name__=='__main__':main()

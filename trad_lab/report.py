"""Local JSON/Markdown reports. Raw audio/text never leave the machine."""
import json
from collections import Counter
from pathlib import Path

from .glossary import load, shadow
from .metrics import term_inventory, metrics
from .runner import save


def pct(value):return 'undefined' if value is None else f'{value*100:.2f}%'


def reports(out,glossary):
    out=Path(out);document=load(glossary);rows=[];states=[]
    for folder in sorted((out/'models').iterdir()) if (out/'models').exists() else []:
        status=json.loads((folder/'status.json').read_text(encoding='utf-8')) if (folder/'status.json').exists() else {'status':'blocked','reason':'missing status'}
        states.append({'variant':folder.name,**status})
        gpu=json.loads((folder/'gpu_samples.json').read_text(encoding='utf-8')) if (folder/'gpu_samples.json').exists() else {}
        for path in sorted(folder.glob('*/result.json')):
            data=json.loads(path.read_text(encoding='utf-8'));m=metrics(data['reference_raw'],data['hypothesis_raw'])
            for key in ['wer','cer','word_errors','character_errors']:
                if m[key]!=data['metrics'][key]:raise ValueError('Scoring definition changed; do not silently mix metrics')
            save(path.parent/'rescored_metrics.json',m)
            medical=term_inventory(data['reference_raw'],data['hypothesis_raw'],document['terms'])
            save(path.parent/'medical_terms.json',{'method':'exact canonical/variant/alias token counts, no semantic adjudication',
                'terms':medical,'occurrence_deficit':sum(t['occurrence_deficit'] for t in medical)})
            post_path=path.parent/'post_glossary.json'
            if not post_path.exists():save(post_path,shadow(data['reference_raw'],data['hypothesis_raw'],document,data['sample_id']))
            post=json.loads(post_path.read_text(encoding='utf-8'))
            # Cached normalization text stays untouched; review metrics use the
            # current risk policy just like the raw hypothesis above.
            if post.get('status')=='shadow_only_unapproved':
                post['candidate_metrics']=metrics(data['reference_raw'],post['candidate_text'])
                post['controlled_metrics']=metrics(data['reference_raw'],post['controlled_text'])
                save(post_path,post)
            row={'variant':folder.name,'model':data['model'],'sample':data['sample_id'],
                'wer':m['wer'],'cer':m['cer'],'word_errors':m['word_errors'],'reference_words':m['reference_words'],
                'character_errors':m['character_errors'],'reference_characters':m['reference_characters'],
                'rtf':data['rtf'],'asr_wall_s':data['asr_wall_s'],'duration_s':data['audio_duration_s'],
                'gpu_peak_total_used_mib':gpu.get('peak_used_mib'),'gpu_baseline_total_used_mib':gpu.get('baseline_used_mib'),
                'medical_occurrence_deficit':sum(t['occurrence_deficit'] for t in medical),
                'risk_flags':m['risk_flag_counts'],'shadow_wer':post.get('candidate_metrics',{}).get('wer'),
                'controlled_wer':post.get('controlled_metrics',{}).get('wer'),
                'shadow_word_errors':post.get('candidate_metrics',{}).get('word_errors'),
                'controlled_word_errors':post.get('controlled_metrics',{}).get('word_errors'),
                'shadow_corrections':len(post.get('corrections',[])),
                'shadow_suggestions':len(post.get('suggestions',[]))}
            rows.append(row)
            text=f"# {data['sample_id']} / {folder.name}\n\nReference: provisional TurboScribe, reviewed; not certified ground truth.\n\n"
            text+=f"WER **{pct(m['wer'])}**, CER **{pct(m['cer'])}**. S/D/I = {m['substitutions']}/{m['deletions']}/{m['insertions']}.\n\n"
            text+=f"Audio {data['audio_duration_s']:.3f} s; ASR {data['asr_wall_s']:.3f} s; RTF {data['rtf']:.4f}. Model load/warmup, decoding MP3 and scoring excluded.\n\n"
            text+=f"Sampled device VRAM peak {gpu.get('peak_used_mib')} MiB; baseline {gpu.get('baseline_used_mib')} MiB. Aggregate GPU, not exact per-process allocation.\n\n"
            text+=f"Medical term occurrence deficit {row['medical_occurrence_deficit']} (lexical proxy). Risk flags: `{m['risk_flag_counts']}`. These are review candidates, not certified medical errors.\n\n"
            text+=f"Raw signed/comparator/percent measurement signatures changed: {m.get('measurement_signature_review',{}).get('changed','requires report refresh')}. Review rescored_metrics.json; primary punctuation-normalized WER may mask signs.\n\n"
            text+="## Normalization\n\n"+json.dumps(data['normalization'],ensure_ascii=False,indent=2)+"\n\n"
            text+="## Review flags\n\n| Category | Reference context | Hypothesis context |\n|---|---|---|\n"
            for flag in m['risk_flags']:
                a=flag['reference_context'].replace('|','/');b=flag['hypothesis_context'].replace('|','/')
                text+=f"| {', '.join(flag['categories'])} | {a} | {b} |\n"
            text+="\n## Glossary shadow (unapproved)\n\n"
            text+=f"Status: {post['status']}. Candidate WER {pct(row['shadow_wer'])}; controlled spacing-only WER {pct(row['controlled_wer'])}. No activation in LIVE.\n\n"
            text+="## Original hypothesis (before normalization)\n\n```text\n"+data['hypothesis_raw']+"\n```\n\n## Original reference text\n\n```text\n"+data['reference_raw']+"\n```\n"
            (path.parent/'REPORT.md').write_text(text,encoding='utf-8')
    aggregate=[]
    for variant in sorted({r['variant'] for r in rows}):
        group=[r for r in rows if r['variant']==variant]
        words=sum(r['reference_words'] for r in group);chars=sum(r['reference_characters'] for r in group)
        seconds=sum(r['duration_s'] for r in group)
        risk_counts=Counter()
        for r in group:risk_counts.update(r['risk_flags'])
        aggregate.append({'variant':variant,'samples':len(group),'pooled_wer':sum(r['word_errors'] for r in group)/words if words else None,
            'pooled_cer':sum(r['character_errors'] for r in group)/chars if chars else None,
            'corpus_rtf':sum(r['asr_wall_s'] for r in group)/seconds if seconds else None,
            'gpu_peak_total_used_mib':max((r['gpu_peak_total_used_mib'] for r in group if r['gpu_peak_total_used_mib'] is not None),default=None),
            'medical_occurrence_deficit':sum(r['medical_occurrence_deficit'] for r in group),
            'word_errors':sum(r['word_errors'] for r in group),'reference_words':words,
            'risk_flags':dict(risk_counts),
            'shadow_pooled_wer':sum(r['shadow_word_errors'] for r in group)/words if words and all(r['shadow_word_errors'] is not None for r in group) else None,
            'controlled_pooled_wer':sum(r['controlled_word_errors'] for r in group)/words if words and all(r['controlled_word_errors'] is not None for r in group) else None,
            'shadow_corrections':sum(r['shadow_corrections'] for r in group),
            'shadow_suggestions':sum(r['shadow_suggestions'] for r in group)})
    save(out/'summary.json',{'rows':rows,'aggregate':aggregate,'statuses':states,
        'ranking_policy':'No winner declared. Compare baseline only, same complete corpus/profile; context is a separate small-only experiment.',
        'streaming_differential':'Requires authenticated same-PCM capture; offline results alone cannot locate streaming/audio/isolation root cause.'})
    md='# TRAD-LAB / corpus comparison\n\nProvisional references; exact normalized WER/CER, not certified clinical accuracy. No model winner declared.\n\n'
    md+='| Variant | Sample | WER | CER | RTF | Term deficit proxy | Sampled total VRAM MiB |\n|---|---|---:|---:|---:|---:|---:|\n'
    for r in rows:md+=f"| {r['variant']} | {r['sample']} | {pct(r['wer'])} | {pct(r['cer'])} | {r['rtf']:.4f} | {r['medical_occurrence_deficit']} | {r['gpu_peak_total_used_mib']} |\n"
    md+='\n## Pooled corpus results\n\n| Variant | Samples | Pooled WER | Pooled CER | Corpus RTF |\n|---|---:|---:|---:|---:|\n'
    for r in aggregate:md+=f"| {r['variant']} | {r['samples']} | {pct(r['pooled_wer'])} | {pct(r['pooled_cer'])} | {r['corpus_rtf']:.4f} |\n"
    md+='\n## Glossary shadow, full-conference batch\n\n| Variant | Baseline WER | Unapproved candidate WER | Controlled spacing-only WER | Corrections / suggestions |\n|---|---:|---:|---:|---:|\n'
    for r in aggregate:md+=f"| {r['variant']} | {pct(r['pooled_wer'])} | {pct(r['shadow_pooled_wer'])} | {pct(r['controlled_pooled_wer'])} | {r['shadow_corrections']} / {r['shadow_suggestions']} |\n"
    md+='\nNormalizer applied independently to each whole conference for this shadow experiment. This does not reproduce READY segment boundaries or cross-segment context in LIVE. A lower lexical WER alone would not establish clinical safety. All terminology replacements remain unapproved.\n'
    md+='\nPooled metrics sum edit errors and reference lengths; they are not an unweighted mean of sample WER. VRAM is device-wide at 2 s intervals; short peaks can be missed. Three recordings and one run per condition do not establish statistical or thermal acceptance.\n\n## Execution status\n\n'
    for state in states:md+=f"- {state['variant']}: {state['status']} — {state.get('reason','completed')}\n"
    md+='\n## Differential limits\n\nOffline model results do not establish whether streaming, session-language isolation or capture conversion caused an observed live error. Use an authenticated same-PCM streaming capture and compare WLK RAW before SegmentManager with READY after it. No DeepL or LIVE changes were used here.\n'
    (out/'SUMMARY.md').write_text(md,encoding='utf-8')
    print('Reports saved locally:',out/'SUMMARY.md',flush=True)

"""Replay the user's saved reading as text, never as a new voice/provider test."""
from dataclasses import asdict
import json
from pathlib import Path
import re

from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.segment_manager import SegmentConfig
from app.captions.transcript_state import TranscriptState
from app.terminology.rollout import GlossaryConfig, session_normalizer
from app.terminology.streaming_policy import POLICY_VERSION, session_segment_manager

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'benchmarks/glossary_soft_v2'
PHRASES = ('orthostatic hypotension', 'physical inactivity', 'shortness of breath',
           'hyper tension', '10 mm of mercury')


def captured_reading():
    saved = json.loads((OUT/'first_reading.json').read_text(encoding='utf-8'))
    segments = []
    for event in saved['operator_history']['events']:
        message = event['message']
        if message['type'] == 'segmentation':
            normal = {s['segment_id']:s for s in message['normalization']['segments']}
            for segment in message['segmentation']['ready_segments']:
                segments.append(dict(**segment,normalized=normal[segment['id']]['normalized_text']))
    return segments


def split_phrases(segments, text):
    cuts = []
    offset = 0
    for s in segments[:-1]:
        offset += len(s['raw'])
        cuts.append(offset)
        offset += 1
    return [dict(phrase=p,cut=cut) for p in PHRASES
            for match in re.finditer(r'(?<!\w)'+re.escape(p)+r'(?!\w)',text,re.I)
            for cut in cuts if match.start() < cut < match.end()]


def replay(schedule, mode):
    normalizer = session_normalizer(GlossaryConfig(mode=mode,state_path=''),'en',IdentityNormalizer())
    manager = session_segment_manager(normalizer,SegmentConfig(),'reading-'+mode)
    state = TranscriptState()
    rows = []
    now = 0.
    text = ''
    bypasses = []

    def collect(result):
        bypasses.extend(e for e in result.events if e['type']=='medical_boundary_bypass')
        for segment in result.ready_segments:
            normalized = normalizer.normalize(segment.id,segment.text)
            rows.append(dict(raw=segment.text,normalized=normalized.normalized_text,
                reason=segment.reason,emitted_at=segment.emitted_at,latency_ms=segment.latency_ms,
                corrections=[asdict(c) for c in normalized.corrections],
                terminology_context=getattr(normalizer,'translation_context',lambda *args:'')(
                    normalized.normalized_text,'en','es')))

    for when, addition in schedule:
        while now+.1 < when-1e-8:
            now=round(now+.1,6);collect(manager.tick(now))
        now=when
        text=(text+' '+addition).strip()
        state.update(dict(lines=[dict(text=text,speaker=1)],buffer_transcription=''))
        collect(manager.update(state,now))
    collect(manager.tick(now+1))
    collect(manager.finish(now+1.1))
    output=' '.join(r['normalized'] for r in rows)
    assert ' '.join(r['raw'] for r in rows).split()==text.split(),'Raw loss or duplication'
    return dict(mode=mode,segments=len(rows),rows=rows,normalized=output,
        split_phrases=split_phrases(rows,text),boundary_bypasses=bypasses,
        corrections=sum(len(r['corrections']) for r in rows))


def main():
    original=captured_reading()
    raw=' '.join(s['text'] for s in original)
    schedules={
        'recorded_fragment_release_times':[(s['emitted_at'],s['text']) for s in original],
        'controlled_word_stream_400ms':[(i*.4,w) for i,w in enumerate(raw.split())],
    }
    comparisons=[]
    for name,schedule in schedules.items():
        profiles=[replay(schedule,mode) for mode in ['off','soft','shadow']]
        comparisons.append(dict(schedule=name,profiles=profiles))
        soft=profiles[1]
        assert soft['corrections']==len(re.findall(r'\bhyper\s+tension\b',raw,re.I))
        assert not soft['split_phrases'],soft['split_phrases']
        assert re.search(r'5 mg, not 15 mg',soft['normalized'])
        for value in ['primary outlawed','the astolic blood pressure','high rate']:
            assert value in soft['normalized'],value
        assert profiles[0]['normalized']==raw
        assert profiles[2]['normalized']==raw
        print(json.dumps(dict(schedule=name,counts={p['mode']:p['segments'] for p in profiles},
            soft_corrections=soft['corrections'],soft_split_phrases=soft['split_phrases'])),flush=True)
    report=dict(policy=POLICY_VERSION,
        scope='Same saved reading; text replay with recorded fragment-release times and a controlled word stream. '
              'Not a replay of missing full ASR snapshots; no voice inference, live DeepL or OBS test.',
        input_text=raw,observed_original_segments=len(original),
        observed_original_split_phrases=split_phrases([dict(raw=s['text']) for s in original],raw),
        comparisons=comparisons)
    (OUT/'reading_replay.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()

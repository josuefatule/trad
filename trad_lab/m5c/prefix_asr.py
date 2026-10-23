"""Bounded offline DSP A/B; same native M5-A model/profile, no correct prompts."""
import json
from pathlib import Path
import time
from difflib import SequenceMatcher
from trad_lab.m5a.adapter import TurboAdapter
from trad_lab.m5b.model import load_decoder
from trad_lab.m4c.replay import ClosedServices
from trad_lab.audio import digest
from trad_lab.safety import gpu_snapshot


def check(signal,out):
    signal=Path(signal);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    guard=ClosedServices();assert guard.check()['safe']
    before=gpu_snapshot();native=load_decoder(out/'model_runtime');records=[]
    def decode(audio,start):
        assert guard.check()['safe'];words=native(audio,start);assert guard.check()['safe'];return words
    for kind in ('original','fir'):
        src=signal/f'prefix_{kind}.s16le';pcm=src.read_bytes();messages=[];events=[];started=time.perf_counter()
        adapter=TurboAdapter('prefix-'+kind,decode,messages.append,raw_sink=events.append,backend='turbo-experimental');adapter.start()
        sequence=0
        for at in range(0,len(pcm),64000):adapter.push(adapter.session_id,sequence,pcm[at:at+64000]);sequence+=1
        adapter.push(adapter.session_id,sequence,b'')
        confirmed=[w for e in events for w in e.get('confirmed',[])];text=''.join(w['text'] for w in confirmed)
        result={'kind':kind,'source_sha256':digest(src),'bytes':len(pcm),'nominal_s':len(pcm)/32000,'wall_s':time.perf_counter()-started,
                'confirmed':confirmed,'stable_text':text,'tail':adapter.tail,'events':events,'scope':'Incomplete physical prefix, offline FIR comparison; no WER or clinical reference'}
        (out/f'{kind}.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8');records.append(result)
        print(json.dumps({'kind':kind,'confirmed':len(confirmed),'tail':''.join(w['text'] for w in adapter.tail)}),flush=True)
    a,b=(r['stable_text'].split() for r in records)
    differences=[{'operation':tag,'original':' '.join(a[i:j]),'candidate':' '.join(b[k:l])} for tag,i,j,k,l in SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if tag!='equal']
    comparison={'status':'COMPLETED; medical effect requires review','differences':differences,
        'same_model_profile':True,'input_duration_s':[r['nominal_s'] for r in records],'gpu_before':before,'gpu_after_work':gpu_snapshot(),
        'scope':'Hypothesis discrepancies on incomplete prefix; duration/anti-alias correction is not demonstrated medical accuracy improvement.'}
    (out/'comparison.json').write_text(json.dumps(comparison,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'A_B':'complete','discrepancies':differences},ensure_ascii=False))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--signal',required=True);p.add_argument('--out',required=True);a=p.parse_args();check(a.signal,a.out)

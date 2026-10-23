import json,shutil
from pathlib import Path
from trad_lab.audio import digest
from trad_lab.m5c2.prepare import verify as verify_a
ROOT=Path('C:/live-captions')
BASE=ROOT/'logs/trad_lab/m5c2a_retry_20261021T124048Z/environment_a_ready/plan.json'
SHA='b4f0409ec892ee8ce6028a59686b8276b0edf6a81a9472849010177f97bcc914'
def verify(path):
    p=Path(path).resolve();d=json.loads(p.read_text());copy=Path(d['copy']).resolve()
    if not copy.is_relative_to(ROOT/'logs/trad_lab') or copy.name!='copy':raise ValueError('Lab copy required')
    if (d['phase'],d['backend_port'],d['trad_port'],d['deepl_enabled'],d['B_authorized'])!=('M5-C2-B',18000,18010,True,True):raise ValueError('B policy changed')
    for n,h in d['manifest'].items():
        q=(copy/n).resolve()
        if not q.is_relative_to(copy) or digest(q)!=h:raise ValueError('Frozen B source changed: '+n)
    actual={q.relative_to(copy).as_posix() for q in copy.rglob('*') if q.is_file() and '__pycache__' not in q.parts and '.runtime' not in q.parts}
    if actual!=set(d['manifest']):raise ValueError('Unmanifested B source')
    if digest(copy/'app/static/m5c_resampler.js')!=d['resampler_sha256']:raise ValueError('FIR changed')
    return d
def prepare(out):
    assert digest(BASE)==SHA;old=verify_a(BASE);out=Path(out).resolve();assert out.is_relative_to(ROOT/'logs/trad_lab');out.mkdir(parents=True,exist_ok=False);copy=out/'copy'
    for n,h in old['manifest'].items():
        dst=copy/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(Path(old['copy'])/n,dst);assert digest(dst)==h
    for src in (ROOT/'trad_lab/m5c2b').glob('*'):
        if src.is_file():
            dst=copy/'trad_lab/m5c2b'/src.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    p=copy/'app/main.py';text=p.read_text(encoding='utf-8');assert text.count('from trad_lab.m5c2.runtime import ')==3;p.write_text(text.replace('from trad_lab.m5c2.runtime import ','from trad_lab.m5c2b.runtime import '),encoding='utf-8')
    for n in ('app/templates/operator.html','app/templates/overlay.html','app/templates/m5c_capture.html','app/static/m5b_diagnostics.js'):
        p=copy/n;text=p.read_text(encoding='utf-8');text=text.replace('M5-C2 A','M5-C2 B').replace('ENSAYO A','ENSAYO B').replace('DEEPL OFF','DEEPL REAL EN→ES').replace('DeepL OFF','DeepL REAL EN→ES');p.write_text(text,encoding='utf-8')
    p=copy/'app/static/m5c2_dom.js';text=p.read_text(encoding='utf-8').replace("['partial','confirmed','pending','ready']","['partial','confirmed','pending','ready','english','last-caption']");p.write_text(text,encoding='utf-8')
    manifest={q.relative_to(copy).as_posix():digest(q) for q in copy.rglob('*') if q.is_file()}
    d={**old,'copy':str(copy),'manifest':manifest,'phase':'M5-C2-B','base_plan':str(BASE),'base_plan_sha256':SHA,'deepl_enabled':True,'B_authorized':True,'human_authorization':'User explicitly authorized B with real DeepL EN to ES and experimental OBS; LIVE unchanged','credential_storage':'Read original local .env in process only, never copy or serialize key','max_provider_calls':128,'max_provider_characters':20000}
    (out/'plan.json').write_text(json.dumps(d,indent=2),encoding='utf-8');verify(out/'plan.json');return d
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps({'files':len(prepare(a.out)['manifest'])}))

"""Clone the approved M5-B2 freeze, never the current LIVE app or its secrets."""
import json
from pathlib import Path
import shutil
from trad_lab.audio import digest
from trad_lab.m5b.prepare import verify as verify_b2

ROOT=Path('C:/live-captions')
BASE=ROOT/'logs/trad_lab/m5b2_20261021T035811Z/environment_e2e_delivery/plan.json'
BASE_SHA='577cf8e171e822b23cd7ab3b08c999bd374e0f04ecddc02aa5e021d3a8b48cd5'


def prepare(out):
    if digest(BASE)!=BASE_SHA:raise ValueError('Approved M5-B2 plan changed')
    old=verify_b2(BASE)
    out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'logs/trad_lab'):raise ValueError('Private lab path required')
    out.mkdir(exist_ok=False,parents=True);copy=out/'copy'
    for name,sha in old['manifest'].items():
        src=Path(old['copy'])/name;dst=copy/name
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        if digest(src)!=sha or digest(dst)!=sha:raise ValueError('Concurrent base edit')
    for src in (ROOT/'trad_lab/m5c').glob('*'):
        if src.is_file():
            dst=copy/'trad_lab/m5c'/src.name;dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst)
    def patch(name,old,new):
        path=copy/name;text=path.read_text(encoding='utf-8')
        if text.count(old)!=1:raise ValueError('Copy patch anchor changed: '+name)
        path.write_text(text.replace(old,new),encoding='utf-8',newline='\n')
    patch('app/main.py','from trad_lab.m5b.runtime import configure_environment','from trad_lab.m5c.runtime import configure_environment')
    patch('app/main.py','from app.translation.engine import provider_from_config','from trad_lab.m5c.runtime import provider_from_config')
    patch('app/main.py','    install(app)\n    return app','    install(app)\n    from trad_lab.m5c.runtime import install as install_c1\n    install_c1(app)\n    return app')
    patch('trad_lab/m5b/serve.py','    if args.authorization!=AUTHORIZATION:',
          "    raise RuntimeError('M5-C1 is offline-only; prepare a newly authorized C2 plan before TCP')\n    if args.authorization!=AUTHORIZATION:")
    patch('app/static/operator.js','window.open("/m5b/file-capture",','window.open("/m5c/physical-capture",')
    patch('app/templates/operator.html','</head>','<script defer src="/static/m5c_controls.js"></script></head>')
    patch('app/overlay/hub.py','        text = result.translated_text or ""',
          '''        if getattr(self, '_m5c_hidden', False):
            self._event("translator", state="operator_hidden", sequence=result.sequence)
            return False
        text = result.translated_text or ""''')
    # Keep hidden until explicit owner action, including across new sessions.
    for src,name in [('physical_capture.html','app/templates/m5c_capture.html'),
                     ('physical_capture.js','app/static/m5c_capture.js'),
                     ('physical_core.cjs','app/static/m5c_physical_core.js'),
                     ('resampler.cjs','app/static/m5c_resampler.js'),
                     ('resample_worker.js','app/static/m5c_worker.js'),
                     ('worklet.js','app/static/m5c_worklet.js'),
                     ('controls.js','app/static/m5c_controls.js')]:
        shutil.copyfile(ROOT/'trad_lab/m5c'/src,copy/name)
    for name in ('app/templates/operator.html','app/templates/overlay.html'):
        path=copy/name;text=path.read_text(encoding='utf-8')
        path.write_text(text.replace('<body>','<body><div style="position:fixed;top:0;left:0;z-index:9999;background:#591b1b;color:white;padding:6px">M5-C1 · SIMULACIÓN · NO USO CLÍNICO</div>'),encoding='utf-8')
    manifest={p.relative_to(copy).as_posix():digest(p) for p in copy.rglob('*') if p.is_file()}
    plan={**old,'copy':str(copy),'manifest':manifest,'phase':'M5-C1',
          'base_plan':str(BASE),'base_plan_sha256':BASE_SHA,'mock_translation':True,
          'physical_prepared':True,'microphone_enabled':False,'deepl_enabled':False,
          'human_authorization':'C1 in-memory/offline only; TCP, microphone, DeepL and OBS require new C2 approval',
          'services_started':False,'resampler_selection':'candidate, subject to offline signal/ASR review; not physically authorized'}
    (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
    return plan


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps({'files':len(prepare(a.out)['manifest']),'services_started':False}))

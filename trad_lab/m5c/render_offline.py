"""Original overlay in headless Chrome over file://; fake wire, no TCP server."""
import json
from pathlib import Path
import subprocess


def check(copy,evidence,out):
    copy=Path(copy).resolve();evidence=Path(evidence);out=Path(out).resolve();out.mkdir(exist_ok=False,parents=True)
    events=json.loads(evidence.read_text(encoding='utf-8'));captions=[e for e in events if e['type']=='caption']
    clear=next(e for e in events if e['type']=='captions_cleared')
    after=next(e for e in captions if e['visual_generation']==clear['visual_generation'] and e['caption']['sequence']>clear['cleared_through_sequence'])
    before=next(e for e in captions if e['visual_generation']<clear['visual_generation'])
    session=next(e for e in events if e['type']=='session' and e['state']=='connecting')
    live=next(e for e in events if e['type']=='session' and e['state']=='live')
    # Exact config parsed from original dataclass; no renderer/layout replacement.
    from app.overlay.config import CaptionConfig
    config=CaptionConfig().to_dict()
    harness='''<script>
    window.fetch=async()=>({ok:true,json:async()=>(CONFIG)});
    window.errors=[];addEventListener('error',e=>errors.push(e.message));
    window.checks={};
    class LocalWire{
      static OPEN=1;constructor(){this.readyState=1;setTimeout(()=>{
        this.onopen?.();
        const emit=m=>this.onmessage?.({data:JSON.stringify(m)});
        emit(EVENTS[0]);emit(EVENTS[1]);emit(EVENTS[2]);
        setTimeout(()=>{checks.before_clear=!document.getElementById('caption').hidden;emit(EVENTS[3]);},200);
        setTimeout(()=>{checks.clear_empty=document.getElementById('caption').hidden&&document.getElementById('caption').textContent==='';emit(EVENTS[4]);},400);
        setTimeout(()=>{checks.target_es=document.documentElement.lang==='es';checks.shown=!document.getElementById('caption').hidden;
          checks.no_errors=errors.length===0;
          const p=document.createElement('pre');p.hidden=true;p.id='test-result';p.textContent=JSON.stringify({checks,errors});document.body.append(p);
          document.title=Object.values(checks).every(Boolean)?'M5C_OFFLINE_PASS':'M5C_OFFLINE_FAIL';},800);
      },20);}send(){}close(){this.readyState=3;}}
    window.WebSocket=LocalWire;
    </script>'''.replace('CONFIG',json.dumps(config)).replace('EVENTS',json.dumps([session,live,before,clear,after],ensure_ascii=False))
    html=(copy/'app/templates/overlay.html').read_text(encoding='utf-8')
    html=html.replace('src="/static/','src="'+(copy/'app/static').as_uri()+'/').replace('href="/static/','href="'+(copy/'app/static').as_uri()+'/')
    html=html.replace('<head>','<head>'+harness)
    page=out/'overlay_offline.html';page.write_text(html,encoding='utf-8')
    command=['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless','--disable-gpu','--no-first-run',
        '--disable-background-networking','--disable-extensions','--disable-sync','--no-default-browser-check',
        '--user-data-dir='+str(out/'private_chrome_profile'),'--allow-file-access-from-files','--hide-scrollbars',
        '--window-size=1920,1080','--virtual-time-budget=1500','--screenshot='+str(out/'overlay.png'),'--dump-dom',page.as_uri()]
    result=subprocess.run(command,capture_output=True,timeout=40)
    dom=result.stdout.decode('utf-8','replace');(out/'dom.html').write_text(dom,encoding='utf-8')
    (out/'chrome.stderr.log').write_bytes(result.stderr)
    record={'returncode':result.returncode,'pass':'<title>M5C_OFFLINE_PASS</title>' in dom,
            'scope':'Original overlay HTML/CSS/JS/renderer, file:// and local fake WebSocket, real Chrome headless. No TCP, OBS or real provider; DOM not projector photons.',
            'screenshot':str(out/'overlay.png')}
    (out/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    assert result.returncode==0 and record['pass'],record
    print(json.dumps(record))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--copy',required=True);p.add_argument('--evidence',required=True);p.add_argument('--out',required=True);a=p.parse_args();check(a.copy,a.evidence,a.out)

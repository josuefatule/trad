"""Real Chrome canvas/DOM, recorded B captions, file:// only. No services or API."""
import json
from pathlib import Path
import subprocess


def check(copy, out):
    copy=Path(copy).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    old=Path('C:/live-captions/logs/trad_lab/m5c2b_20261021T130251Z')
    config=json.loads((old/'latest_status.json').read_text(encoding='utf-8'))['status']['caption_config'];config['mode']='timed_queue'
    rows=[json.loads(line) for line in (old/'overlay_wire.jsonl').read_text(encoding='utf-8').splitlines()]
    captions=[row['message']['caption'] for row in rows if row['message']['type']=='caption']
    assets=(copy/'app/static').as_uri()
    html='''<!doctype html><meta charset="utf-8"><title>RUNNING</title>
    <link rel="stylesheet" href="ASSETS/overlay.css">
    <div id="overlay-canvas"><div id="caption-stage"><div id="caption" hidden></div></div></div>
    <script src="ASSETS/overlay_geometry.js"></script><script src="ASSETS/caption_renderer.js"></script>
    <script>
    const config=CONFIG,captions=CAPTIONS,errors=[];addEventListener('error',e=>errors.push(e.message));
    const el=document.getElementById('caption'),canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');
    const effective=OverlayGeometry.apply(config,1920,1080,document.getElementById('overlay-canvas'),document.getElementById('caption-stage'),el).config;
    let now=0,id=0;const timers=new Map(),shown=[],drops=[];
    const renderer=new CaptionPresentation.CaptionRenderer(effective,{now:()=>now,
      measure:(text,size)=>{ctx.font=`600 ${size}px Arial`;return ctx.measureText(text).width;},
      show:f=>{el.textContent=f.text;el.style.fontSize=f.fontSize+'px';el.style.maxWidth=effective.max_width+'px';el.hidden=false;el.classList.add('visible');shown.push({text:f.text,sequence:f.caption.sequence});},
      hide:()=>{el.hidden=true;el.classList.remove('visible');el.textContent='';},
      report:(reason,count)=>drops.push({reason,count}),schedule:(fn,ms)=>{timers.set(++id,{fn,at:now+ms});return id;},cancel:i=>timers.delete(i)});
    function advance(end){while(true){const t=[...timers].sort((a,b)=>a[1].at-b[1].at)[0];if(!t||t[1].at>end)break;now=t[1].at;timers.delete(t[0]);t[1].fn();}now=end;}
    renderer.reset(captions[0].session_id);renderer.setState('live');
    for(const caption of captions){renderer.enqueue(caption);advance(now+60000);}
    const clean=t=>t.replace(/\\s+/gu,' ').trim();
    const exact=captions.every(c=>clean(shown.filter(f=>f.sequence===c.sequence).map(f=>f.text).join(' '))===clean(c.text));
    // Leave the previously affected 49 visible for a real screenshot/geometry check.
    renderer.reset('probe');renderer.setState('live');renderer.enqueue({...captions.find(c=>c.sequence===49),session_id:'probe'});
    const rect=el.getBoundingClientRect(),stage=document.getElementById('caption-stage').getBoundingClientRect();
    const checks={all_51_exact:exact,zero_drops:drops.length===0,probe_two_lines:el.textContent.split('\\n').length<=effective.max_lines,
      probe_not_clipped:rect.left>=stage.left&&rect.right<=stage.right&&rect.top>=stage.top&&rect.bottom<=stage.bottom,
      probe_visible:!el.hidden,no_js_errors:errors.length===0};
    document.documentElement.lang='es';document.title=Object.values(checks).every(Boolean)?'REPAIR_PASS':'REPAIR_FAIL';
    const result=document.createElement('script');result.type='application/json';result.id='repair-result';result.textContent=JSON.stringify({checks,drops,errors,pages:shown.length-1,probe_text:el.textContent});document.body.append(result);
    </script>'''.replace('ASSETS',assets).replace('CONFIG',json.dumps(config)).replace('CAPTIONS',json.dumps(captions,ensure_ascii=False))
    page=out/'overlay_probe.html';page.write_text(html,encoding='utf-8')
    command=['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless','--disable-gpu','--no-first-run','--disable-background-networking','--disable-extensions','--disable-sync','--no-default-browser-check',
             '--user-data-dir='+str(out/'private_chrome_profile'),'--allow-file-access-from-files','--hide-scrollbars','--window-size=1920,1080','--virtual-time-budget=500','--screenshot='+str(out/'overlay.png'),'--dump-dom',page.as_uri()]
    result=subprocess.run(command,capture_output=True,timeout=40)
    dom=result.stdout.decode('utf-8','replace');(out/'dom.html').write_text(dom,encoding='utf-8');(out/'chrome.stderr.log').write_bytes(result.stderr)
    record={'status':'PASS' if '<title>REPAIR_PASS</title>' in dom else 'FAIL','returncode':result.returncode,
            'scope':'51 preserved Spanish captions through repaired renderer with real Chrome canvas/DOM; sequential offline drain; final seq49 screenshot; no TCP, OBS, model, mic or provider calls'}
    (out/'result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record));assert record['status']=='PASS' and result.returncode==0


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--copy',required=True);p.add_argument('--out',required=True);a=p.parse_args();check(a.copy,a.out)

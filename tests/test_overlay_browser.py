"""Real Chromium layout checks, isolated profile and fixtures; no WLK/DeepL/OBS."""
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from app.overlay.config import CaptionConfig


ROOT = Path(__file__).resolve().parents[1]


class OverlayBrowserTests(unittest.TestCase):
    def setUp(self):
        self.browser = (shutil.which("chromium") or shutil.which("google-chrome") or
                   next((str(path) for path in (
                       Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) /
                       "Google/Chrome/Application/chrome.exe",
                       Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) /
                       "Microsoft/Edge/Application/msedge.exe") if path.exists()), None))
        if not self.browser:
            self.skipTest("Chromium/Chrome/Edge unavailable for real layout test")

    def render_fixture(self, page, budget=1500):
        with tempfile.TemporaryDirectory(prefix="caption-layout-") as directory:
            fixture = Path(directory) / "layout.html"
            fixture.write_text(page, encoding="utf-8")
            result = subprocess.run([self.browser, "--headless=new", "--disable-gpu", "--no-first-run",
                                     "--no-default-browser-check", "--disable-background-networking",
                                     "--allow-file-access-from-files", "--window-size=1920,1080",
                                     "--user-data-dir=" + str(Path(directory) / "profile"),
                                     "--virtual-time-budget=" + str(budget), "--dump-dom", fixture.as_uri()],
                                    capture_output=True, encoding="utf-8", errors="replace", timeout=45)
            match = re.search(r'<pre id="test-result"[^>]*>(.*?)</pre>', result.stdout, re.S)
            self.assertIsNotNone(match, "Browser did not return layout results: " + result.stderr[-1500:])
            report = json.loads(html.unescape(match.group(1)))
            self.assertTrue(report["ok"], report)
            return report

    def test_real_canvas_wrapping_and_dom_stay_inside_caption_region(self):
        config = CaptionConfig().to_dict()
        page = (ROOT / "app/templates/overlay.html").read_text(encoding="utf-8")
        static = (ROOT / "app/static").as_uri()
        page = page.replace('/static/', static + '/')
        bootstrap = """
        <script>
        window.layoutErrors=[];
        window.addEventListener('error',event=>layoutErrors.push(event.message || event.target.src),true);
        console.error=(...args)=>layoutErrors.push(args.join(' '));
        window.fetch = async () => ({ok:true,json:async()=>(CONFIG)});
        window.WebSocket = class {
          static OPEN=1;
          constructor(){this.readyState=1;window.testSocket=this;}
          send(){} close(){this.readyState=3;}
        };
        </script>
        """.replace("CONFIG", json.dumps(config))
        page = page.replace("</head>", bootstrap + "</head>")
        checks = """
        <pre id="test-result" style="display:none"></pre><script>
        setTimeout(() => {
          const results=[];
          const check=(condition,message)=>{if(!condition)throw Error(message);};
          const config=CONFIG;
          const caption=document.getElementById('caption'), stage=document.getElementById('caption-stage');
          const surface=document.getElementById('overlay-canvas');
          const measureCanvas=document.createElement('canvas').getContext('2d');
          const measure=(text,size)=>{measureCanvas.font=`600 ${size}px Arial`; return measureCanvas.measureText(text).width;};
          const validate=(settings,frame,label)=>{
            const rect=caption.getBoundingClientRect(), region=stage.getBoundingClientRect();
            const lines=frame.text.split('\\n');
            check(lines.length<=settings.max_lines,label+': line count');
            check(lines.every(line=>measure(line,frame.fontSize)<=settings.max_width+.1),label+': width');
            check(rect.top>=region.top+settings.padding_y-.1,label+': top');
            check(rect.bottom<=region.bottom-settings.padding_y+.1,label+': bottom');
            check(rect.left>=region.left+settings.padding_x-.1,label+': left');
            check(rect.right<=region.right-settings.padding_x+.1,label+': right');
            check(Math.abs((rect.top+rect.bottom-region.top-region.bottom)/2)<.1,label+': vertical center');
            check(Math.abs((rect.left+rect.right-region.left-region.right)/2)<.1,label+': horizontal center');
            check(Math.abs(rect.height-lines.length*settings.font_size*settings.line_height)<.2,label+': CSS line height');
            check(getComputedStyle(caption).overflow!=='hidden',label+': no concealed clipping');
            check(frame.fontSize===settings.font_size,label+': unchanged font');
            results.push({label,lines:lines.length,top:rect.top,bottom:rect.bottom,font:frame.fontSize});
          };
          try {
            check(window.testSocket?.onmessage,'production overlay initialized: '+JSON.stringify(window.layoutErrors));
            const send=data=>testSocket.onmessage({data:JSON.stringify({protocol_version:2,...data})});
            send({type:'snapshot',event_id:0,session_id:'layout',state:'live',captions:[]});
            const text='Systolic and diastolic pressure, cardiovascular function and vascular resistance. Café, naïve — whole words stay together. '.repeat(6);
            send({type:'caption',event_id:1,session_id:'layout',caption:{session_id:'layout',sequence:1,provider:'deepl',text}});
            // Use the complete logical canvas at 1:1 for precise geometry assertions.
            const effective=OverlayGeometry.apply(config,1920,1080,surface,stage,caption).config;
            validate(effective,{text:caption.textContent,fontSize:parseFloat(caption.style.fontSize)},'production 48px / 2 lines');
            check(caption.textContent.split('\\n').length===2,'default uses both available lines');
            check(stage.getBoundingClientRect().top===930,'slide exclusion boundary');
            check(getComputedStyle(caption).backgroundColor==='rgba(0, 0, 0, 0)','transparent caption');
            check(getComputedStyle(document.body).backgroundColor==='rgba(0, 0, 0, 0)','transparent outside region');
            const before=caption.textContent;
            send({type:'caption',event_id:2,session_id:'layout',caption:{session_id:'layout',sequence:1,provider:'deepl',text:'DUPLICATE'}});
            check(caption.textContent===before,'production sequence deduplication');
            for (const overrides of [{font_size:36},{max_lines:2,region_width:700,region_x:600},
              {font_size:64,region_height:150},{font_size:48,region_y:900,region_height:180}]) {
              const c={...config,...overrides};
              const settings=OverlayGeometry.apply(c,1920,1080,surface,stage,caption).config;
              const renderer=new CaptionPresentation.CaptionRenderer(settings,{measure,now:()=>0,
                show:frame=>{caption.hidden=false;caption.textContent=frame.text;caption.style.fontSize=`${frame.fontSize}px`;validate(settings,frame,JSON.stringify(overrides));},hide:()=>{},report:()=>{}});
              renderer.reset('fixture');renderer.setState('live');
              for(let i=1;i<=8;i++)renderer.enqueue({session_id:'fixture',sequence:i,provider:'deepl',text});
            }
            document.getElementById('test-result').textContent=JSON.stringify({ok:true,checks:results.length,results});
          } catch(error) {document.getElementById('test-result').textContent=JSON.stringify({ok:false,error:String(error)});}
        },300);
        </script>
        """.replace("CONFIG", json.dumps(config))
        page = page.replace("</body>", checks + "</body>")
        self.assertEqual(self.render_fixture(page)["checks"], 33)

    def test_preview_displays_complete_canvas_and_caption_band(self):
        config = CaptionConfig().to_dict()
        page = (ROOT / "app/templates/overlay_preview.html").read_text(encoding="utf-8")
        page = page.replace('/static/', (ROOT / "app/static").as_uri() + '/')
        page = page.replace("</head>", "<script>window.fetch=async()=>({ok:true,json:async()=> (" +
                            json.dumps(config) + ")});</script></head>")
        checks = """
        <pre id="test-result" style="display:none"></pre><script>
        setTimeout(()=>document.getElementById('play').click(),300);
        setTimeout(()=>{
          const check=(condition,message)=>{if(!condition)throw Error(message);};
          try {
            const canvas=document.getElementById('overlay-canvas').getBoundingClientRect();
            const band=document.getElementById('preview-band').getBoundingClientRect();
            const caption=document.getElementById('caption').getBoundingClientRect();
            const scale=canvas.width/1920;
            check(canvas.left>=0 && canvas.right<=innerWidth+.1,'full width visible');
            check(canvas.top>=0 && canvas.bottom<=innerHeight+.1,'full height visible');
            check(Math.abs(canvas.width/canvas.height-1920/1080)<.001,'canvas aspect ratio');
            check(Math.abs(band.top-canvas.top-930*scale)<.1,'band Y=930');
            check(Math.abs(band.bottom-canvas.bottom)<.1,'band ends at 1080');
            check(caption.top>=band.top && caption.bottom<=band.bottom,'demo stays inside band');
            check(!document.getElementById('caption').hidden,'demo visible');
            check(document.getElementById('geometry-status').textContent.includes('2/3 lines'),'height warning');
            check(getComputedStyle(document.getElementById('caption')).fontSize==='48px','logical font unchanged');
            document.getElementById('test-result').textContent=JSON.stringify({ok:true});
          }catch(error){document.getElementById('test-result').textContent=JSON.stringify({ok:false,error:String(error)});}
        },6000);
        </script>
        """
        self.render_fixture(page.replace("</body>", checks + "</body>"), budget=6500)

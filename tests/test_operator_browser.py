"""Exact-viewport Chrome layout and screenshots; fixture status, no microphone/API."""
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from urllib.request import urlopen

from websockets.sync.client import connect
from tests import test_overlay_browser as browser_helpers
ROOT = browser_helpers.ROOT


class OperatorBrowserTests(unittest.TestCase):
    setUp = browser_helpers.OverlayBrowserTests.setUp

    def test_responsive_console_exact_viewports_and_visual_artifacts(self):
        page=(ROOT/"app/templates/operator.html").read_text(encoding="utf-8")
        page=page.replace('/static/',(ROOT/"app/static").as_uri()+'/')
        status={"protocol_version":1,"session_id":"visual-fixture","state":"live","can_start":False,
                "owns_session":True,"overlay_connections":2,"sequence":3,"visual_generation":0,
                "caption_config":{"mode":"persistent_rolling","max_lines":3},"translator_verified":True,
                "translator":{"state":"ready","provider":"deepl"},"latency_diagnostics":{
                    "backend_samples":[],"observers":[],"translation_queue_depth":0}}
        bootstrap={"protocol_version":1,"capabilities":{"operator_console":1,"captions_clear":1},
                   "control_token":"visual-test-token","diagnostics_config":{"minimum_samples":5,
                   "poll_seconds":2,"sustained_seconds":6,"queue_depth_warning":3,"queue_delay_warning_ms":1000,"render_warning_ms":500}}
        setup="<script>window.layoutErrors=[];window.addEventListener('error',event=>layoutErrors.push(event.message || event.target.src),true);window.addEventListener('unhandledrejection',event=>layoutErrors.push(String(event.reason)));window.fetch=async url=>({ok:true,json:async()=>url.includes('bootstrap')?BOOT:STATUS});".replace("BOOT",json.dumps(bootstrap)).replace("STATUS",json.dumps(status))
        setup+="Object.defineProperty(navigator,'mediaDevices',{value:{enumerateDevices:async()=>[]}});</script>"
        page=page.replace('</head>',setup+'</head>')
        check="""
        <script>setTimeout(async()=>{try {
          await OperatorUI.ready;
          OperatorUI.localActive=true;OperatorUI.phaseTo('LIVE');
          document.getElementById('connection').textContent='Connected · fixture';
          document.getElementById('selected-microphone').textContent='Blue Yeti · fixture';
          document.getElementById('control-notice').textContent='Visual QA fixture — no microphone or API calls';
          flow('english',('High blood pressure is a cardiovascular condition characterized by persistently elevated systolic or diastolic blood pressure. ' ).repeat(18));
          flow('normalized',('La hipertensión arterial es una condición cardiovascular caracterizada por una elevación persistente de la presión arterial sistólica y/o diastólica. ').repeat(15));
          flow('confirmed',('La hipertensión arterial es una condición cardiovascular caracterizada por una elevación persistente de la presión arterial systólica y/o diastólica. ').repeat(15));
          const checks=[];const assert=(ok,label)=>{if(!ok)throw Error(label);checks.push(label);};
            assert(document.documentElement.scrollWidth<=innerWidth,'no horizontal scroll');
            const header=document.querySelector('header').getBoundingClientRect();
            for(const id of ['start','stop','clear','microphone']) {
              const rect=document.getElementById(id).getBoundingClientRect();
              assert(rect.left>=0 && rect.right<=innerWidth && rect.top>=0 && rect.bottom<=innerHeight,id+' visible');
            }
            const english=document.getElementById('english'), normalized=document.getElementById('normalized');
            assert(parseFloat(getComputedStyle(english).fontSize)>parseFloat(getComputedStyle(normalized).fontSize),'English predominant');
            assert(english.scrollHeight>english.clientHeight,'internal history scroll');
            assert(english.getBoundingClientRect().bottom<=innerHeight,'monitoring fits laptop');
            assert(getComputedStyle(normalized).whiteSpace==='normal','compact reflow');
            assert(!document.getElementById('stop').disabled,'LIVE stop permitted');
            assert(document.getElementById('start').disabled,'LIVE duplicate start disabled');
            document.querySelector('.diagnostics').open=true;
            document.getElementById('overlay-diagnostics').textContent+='\\n'+('technical audit '.repeat(400));
            window.scrollTo(0,document.body.scrollHeight);
            assert(document.querySelector('header').getBoundingClientRect().top>=-.1,'sticky controls');
            assert(document.documentElement.scrollWidth<=innerWidth,'diagnostics no horizontal scroll');
            window.scrollTo(0,0);document.querySelector('.diagnostics').open=false;
            window.layoutReport={ok:true,width:innerWidth,height:innerHeight,checks};
          }catch(error){window.layoutReport={ok:false,error:String(error)};}
        },200);</script>
        """
        page=page.replace('</body>',check+'</body>')
        # Inline trusted local assets: no file-navigation restrictions or network requests.
        static=(ROOT/"app/static").as_uri()
        page=page.replace(f'<link rel="stylesheet" href="{static}/operator.css">',
                          '<style>'+(ROOT/"app/static/operator.css").read_text(encoding="utf-8")+'</style>')
        for name in ("operator_console.js","operator.js","overlay_diagnostics.js"):
            page=page.replace(f'<script src="{static}/{name}"></script>',
                              '<script>'+(ROOT/"app/static"/name).read_text(encoding="utf-8")+'</script>')
        with tempfile.TemporaryDirectory(prefix="operator-layout-") as directory:
            directory=Path(directory);fixture=directory/"operator.html";fixture.write_text(page,encoding="utf-8")
            process=subprocess.Popen([self.browser,"--headless=new","--disable-gpu","--no-first-run",
                "--no-default-browser-check","--disable-background-networking","--allow-file-access-from-files",
                "--remote-debugging-port=0","--user-data-dir="+str(directory/"profile"),fixture.as_uri()],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+10
                active=directory/"profile/DevToolsActivePort"
                while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
                self.assertTrue(active.exists(),"Headless debugging port unavailable")
                port=active.read_text().splitlines()[0]
                with urlopen(f"http://127.0.0.1:{port}/json",timeout=3) as response:
                    target=next(item for item in json.load(response) if item["type"]=="page")
                with connect(target["webSocketDebuggerUrl"],proxy=None) as socket:
                    serial=0
                    def call(method,params=None):
                        nonlocal serial
                        serial+=1;identifier=serial
                        socket.send(json.dumps({"id":identifier,"method":method,"params":params or {}}))
                        while True:
                            message=json.loads(socket.recv(timeout=10))
                            if message.get("id")==identifier:
                                self.assertNotIn("error",message)
                                return message.get("result",{})
                    for width,height in ((1366,768),(1920,1080)):
                        with self.subTest(viewport=(width,height)):
                            call("Emulation.setDeviceMetricsOverride",{"width":width,"height":height,"deviceScaleFactor":1,"mobile":False})
                            # Re-evaluate assertions after resizing the same fully loaded fixture.
                            call("Runtime.evaluate",{"expression":"window.layoutReport=null;"+check.replace('<script>','').replace('</script>','')})
                            report=None;deadline=time.monotonic()+10
                            while time.monotonic()<deadline:
                                value=call("Runtime.evaluate",{"expression":"JSON.stringify(window.layoutReport)","returnByValue":True}).get("result",{}).get("value")
                                if value and value!="null":
                                    report=json.loads(value);break
                                time.sleep(.05)
                            errors=call("Runtime.evaluate",{"expression":"JSON.stringify({errors:window.layoutErrors,url:location.href,html:document.documentElement.outerHTML.slice(0,1600)})","returnByValue":True})
                            self.assertIsNotNone(report,"Layout script did not complete: "+str(errors))
                            self.assertTrue(report["ok"],report)
                            self.assertEqual((report["width"],report["height"]),(width,height))
                            screenshot=call("Page.captureScreenshot",{"format":"png"})["data"]
                            (ROOT/f"logs/m6-operator-{width}x{height}.png").write_bytes(base64.b64decode(screenshot))
            finally:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)

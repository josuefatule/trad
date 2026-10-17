"""Real Chrome + real local ASGI/WS, fake media device and fake WLK, no DeepL."""
import asyncio
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.request import urlopen

import uvicorn
from websockets.asyncio.server import serve
from websockets.sync.client import connect
from app.main import Settings,create_app
from app.translation import TranslationConfig
from tests import test_overlay_browser as browser_helpers


class RecoveryBrowserTests(unittest.IsolatedAsyncioTestCase):
    setUp=browser_helpers.OverlayBrowserTests.setUp

    async def test_chrome_popup_audio_survives_console_reload_then_owner_stop(self):
        connections=[];audio_frames=[];eof=[]
        async def wlk(ws):
            connections.append(1)
            await ws.send('{"type":"config","useAudioWorklet":true,"mode":"full"}')
            async for data in ws:
                if not data:
                    eof.append(1);await ws.send('{"type":"ready_to_stop"}');return
                audio_frames.append(len(data))
                await ws.send('{"lines":[{"speaker":1,"text":"Texto de prueba."}],"buffer_transcription":""}')
        async with serve(wlk,"127.0.0.1",0) as upstream:
            settings=Settings(log_dir="logs/tests",translation=TranslationConfig(),wlk_url=f"ws://127.0.0.1:{upstream.sockets[0].getsockname()[1]}/asr")
            app=create_app(settings)
            # Bind before launch so the selected ephemeral HTTP port cannot race.
            bound=socket.socket();bound.bind(("127.0.0.1",0));bound.listen(128)
            base=f"http://127.0.0.1:{bound.getsockname()[1]}"
            server=uvicorn.Server(uvicorn.Config(app,log_level="error",lifespan="on"))
            thread=threading.Thread(target=lambda:server.run(sockets=[bound]),daemon=True)
            thread.start()
            def browser():
                with tempfile.TemporaryDirectory(prefix="m7-recovery-") as directory:
                    folder=Path(directory)
                    process=subprocess.Popen([self.browser,"--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check",
                        "--disable-background-networking","--use-fake-device-for-media-stream","--use-fake-ui-for-media-stream",
                        "--remote-debugging-port=0","--user-data-dir="+str(folder/"profile"),base+"/operator"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    try:
                        deadline=time.monotonic()+12;active=folder/"profile/DevToolsActivePort"
                        while (not active.exists() or not server.started) and time.monotonic()<deadline:time.sleep(.05)
                        self.assertTrue(active.exists());port=active.read_text().splitlines()[0]
                        with urlopen(f"http://127.0.0.1:{port}/json",timeout=3) as response:
                            target=next(t for t in json.load(response) if t["type"]=="page" and "/operator" in t["url"])
                        with connect(target["webSocketDebuggerUrl"],proxy=None) as cdp:
                            serial=0
                            def call(method,params=None):
                                nonlocal serial
                                serial+=1;identifier=serial;cdp.send(json.dumps({"id":identifier,"method":method,"params":params or {}}))
                                while True:
                                    message=json.loads(cdp.recv(timeout=10))
                                    if message.get("id")==identifier:
                                        self.assertNotIn("error",message);return message.get("result",{})
                            def evaluate(expression,gesture=False):
                                result=call("Runtime.evaluate",{"expression":expression,"returnByValue":True,"awaitPromise":True,"userGesture":gesture})
                                self.assertNotIn("exceptionDetails",result,result)
                                return result.get("result",{}).get("value")
                            def until(expression):
                                end=time.monotonic()+12
                                while time.monotonic()<end:
                                    if evaluate(expression):return
                                    time.sleep(.1)
                                self.fail("Browser condition timed out: "+expression+"; UI: "+str(evaluate("document.getElementById('error').textContent")))
                            until("globalThis.OperatorUI?.authorized===true")
                            evaluate("document.getElementById('start').click()",True)
                            until("globalThis.OperatorUI?.snapshot?.state==='live'")
                            end=time.monotonic()+10
                            while len(audio_frames)<3 and time.monotonic()<end:time.sleep(.1)
                            self.assertGreaterEqual(len(audio_frames),3,"Popup must really produce fake-media PCM, no autoplay bypass")
                            sid=app.state.caption_hub.session_id;before=len(audio_frames)
                            evaluate("globalThis.m7BeforeReload=true")
                            call("Page.reload")
                            # Page.reload returns before the old document unloads.
                            # Do not mistake its still-LIVE snapshot for recovery.
                            until("globalThis.m7BeforeReload!==true && globalThis.OperatorUI?.snapshot?.owns_session===true && globalThis.OperatorUI?.snapshot?.state==='live'")
                            until("document.getElementById('stop').disabled===false")
                            self.assertEqual(app.state.operator_authority.recoveries,1)
                            self.assertEqual(app.state.caption_hub.session_id,sid)
                            end=time.monotonic()+5
                            while len(audio_frames)<=before and time.monotonic()<end:time.sleep(.1)
                            self.assertGreater(len(audio_frames),before);self.assertEqual(len(connections),1)
                            evaluate("document.getElementById('stop').click()",True)
                            until("globalThis.OperatorUI?.snapshot?.state==='stopped'")
                            self.assertEqual(eof,[1]);self.assertEqual(app.state.operational_run.outcome,"complete")
                            self.assertEqual(app.state.operational_run.translator.queue_depth,0)
                    finally:
                        process.terminate()
                        try:process.wait(timeout=5)
                        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            try:await asyncio.wait_for(asyncio.to_thread(browser),55)
            finally:
                server.should_exit=True;await asyncio.to_thread(thread.join,5);bound.close()
            self.assertFalse(thread.is_alive())

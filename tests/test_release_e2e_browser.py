"""M8 actual isolated Chrome/PCM/ASGI/WS/DOM with timed recorded WLK and fake EN.

No physical microphone, DeepL request, OBS, production ports or external server.
Set M8_E2E_OUTPUT to save correlated clocks from this run (fixture content only).
"""
import asyncio
from contextlib import contextmanager
import copy
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
from urllib.request import urlopen

import uvicorn
from websockets.asyncio.server import serve
from websockets.sync.client import connect

from app.main import Settings, create_app
from app.captions.segment_manager import SegmentConfig
from app.captions.terminology_normalizer import NormalizerConfig
from app.translation import TranslationConfig, TranslatorProvider
from app.translation.engine import TranslationStatus
from benchmarks.release_validation import summarize_pipeline
from benchmarks.segment_latency_ab import ROOT, digest, final_words, load_fixture
from tests import test_overlay_browser as browser_helpers


@contextmanager
def page_connection(port, target):
    with connect(target, proxy=None) as ws:
        serial = 0

        def call(method, params=None):
            nonlocal serial
            serial += 1
            ws.send(json.dumps({"id": serial, "method": method, "params": params or {}}))
            while True:
                message = json.loads(ws.recv(timeout=10))
                if message.get("id") == serial:
                    if "error" in message:
                        raise AssertionError(message["error"])
                    return message.get("result", {})

        def evaluate(expression, gesture=False):
            result = call("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                              "awaitPromise": True, "userGesture": gesture})
            if "exceptionDetails" in result:
                raise AssertionError(result["exceptionDetails"])
            return result.get("result", {}).get("value")

        yield call, evaluate


class ReleaseBrowserTests(unittest.IsolatedAsyncioTestCase):
    setUp = browser_helpers.OverlayBrowserTests.setUp

    async def test_timed_medical_pipeline_clear_reconnect_reload_stop_and_new_session(self):
        fixture_path = ROOT / "benchmarks/medical_full_receive.json.gz"
        events = load_fixture(fixture_path)["events"]
        connections, frames, eof, requests, captions = [], [], [], [], []
        finished = threading.Event()

        async def wlk(ws):
            number = len(connections) + 1
            connections.append(number)
            lang = parse_qs(urlsplit(ws.request.path).query)["language"][0]
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full", "session_language":lang,"session_language_isolation":1}))
            producer = None

            async def feed():
                if number == 1:
                    origin = asyncio.get_running_loop().time()
                    for event in events:
                        await asyncio.sleep(max(0, origin + event["at"] - asyncio.get_running_loop().time()))
                        if event["payload"].get("type") != "ready_to_stop":
                            await ws.send(json.dumps(event["payload"]))
                    finished.set()
                else:
                    await ws.send(json.dumps({"lines": [{"speaker": 1,
                        "text": "No presenta edema. La dosis es 5 mg."}], "buffer_transcription": ""}))
            try:
                async for data in ws:
                    if not data:
                        eof.append(number)
                        if producer:
                            producer.cancel()
                            await asyncio.gather(producer, return_exceptions=True)
                        await ws.send('{"type":"ready_to_stop"}')
                        return
                    frames.append((number, len(data)))
                    if producer is None:
                        producer = asyncio.create_task(feed())
            finally:
                if producer:
                    producer.cancel()
                    await asyncio.gather(producer, return_exceptions=True)

        class FixtureProvider(TranslatorProvider):
            name = "release-fixture"  # Test injection; production's mock filter stays enabled.

            async def translate(self, request):
                requests.append(request)
                await asyncio.sleep(.02)
                return f"Validation caption {request.sequence}."

        async with serve(wlk, "127.0.0.1", 0) as upstream:
            settings = Settings(log_dir="logs/m8-e2e", log_raw=False,
                segments=SegmentConfig(), normalizer=NormalizerConfig(),
                translation=TranslationConfig(enabled=True, provider="test"),
                wlk_url=f"ws://127.0.0.1:{upstream.sockets[0].getsockname()[1]}/asr")
            app = create_app(settings)
            hub = app.state.caption_hub
            publish = hub.publish

            def record(result):
                accepted = publish(result)
                if accepted:
                    captions.append({**copy.deepcopy(hub.last_caption), "visual_generation": hub.visual_generation})
                return accepted

            hub.publish = record  # Test-only observation, no runtime instrumentation change.
            bound = socket.socket()
            bound.bind(("127.0.0.1", 0)); bound.listen(128)
            base = f"http://127.0.0.1:{bound.getsockname()[1]}"
            server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
            report = {}

            def browser():
                def wait(predicate, timeout=15):
                    end = time.monotonic() + timeout
                    while time.monotonic() < end:
                        if predicate():
                            return
                        time.sleep(.05)
                    self.fail("M8 browser condition timed out")

                with tempfile.TemporaryDirectory(prefix="m8-e2e-") as directory:
                    profile = Path(directory) / "profile"
                    process = subprocess.Popen([self.browser, "--headless=new", "--disable-gpu",
                        "--no-first-run", "--no-default-browser-check", "--disable-background-networking",
                        "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
                        "--disable-backgrounding-occluded-windows", "--use-fake-device-for-media-stream",
                        "--use-fake-ui-for-media-stream", "--remote-debugging-port=0",
                        "--user-data-dir=" + str(profile), base + "/operator"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try:
                        active = profile / "DevToolsActivePort"
                        wait(lambda: active.exists() and server.started)
                        port = active.read_text().splitlines()[0]
                        with urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as response:
                            target = next(t for t in json.load(response) if t["type"] == "page")
                        with page_connection(port, target["webSocketDebuggerUrl"]) as (call, evaluate):
                            wait(lambda: evaluate("globalThis.OperatorUI?.authorized===true"))
                            wait(lambda: evaluate("!document.getElementById('direction').disabled"))
                            evaluate("document.getElementById('direction').value='es-en'; document.getElementById('direction').onchange()")
                            overlay = call("Target.createTarget", {"url": base + "/overlay"})["targetId"]
                            with urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as response:
                                overlay_target = next(t for t in json.load(response) if t["id"] == overlay)
                            with page_connection(port, overlay_target["webSocketDebuggerUrl"]) as (overlay_call, overlay_eval):
                                wait(lambda: len(hub.subscribers) == 1)
                                evaluate("document.getElementById('start').click()", True)
                                wait(lambda: evaluate("OperatorUI.snapshot?.state==='live'"))
                                sid = hub.session_id
                                wait(lambda: hub.sequence >= 1)
                                wait(lambda: bool(overlay_eval("document.getElementById('caption').textContent")))
                                before_clear = hub.sequence
                                evaluate("document.getElementById('clear').click()", True)
                                wait(lambda: hub.visual_generation == 1)
                                wait(lambda: overlay_eval("document.getElementById('caption').textContent===''"))
                                self.assertEqual(hub.cleared_through_sequence, before_clear)
                                wait(lambda: hub.sequence > before_clear)
                                wait(lambda: bool(overlay_eval("document.getElementById('caption').textContent")))
                                # Real transport reconnect, snapshot replacement, no duplicate provider call.
                                count = len(requests)
                                overlay_eval("globalThis.m8OldDocument=true")
                                overlay_call("Page.reload")
                                wait(lambda: overlay_eval("globalThis.m8OldDocument!==true && document.getElementById('caption')?.textContent.includes('Validation caption')"))
                                self.assertEqual(len(requests), count)
                                evaluate("globalThis.m8OldDocument=true")
                                call("Page.reload")
                                wait(lambda: evaluate("globalThis.m8OldDocument!==true && OperatorUI?.snapshot?.owns_session===true && OperatorUI?.snapshot?.state==='live' && !document.getElementById('stop').disabled"))
                                self.assertEqual(hub.session_id, sid)
                                self.assertEqual(connections, [1])
                                wait(finished.is_set, timeout=65)
                                evaluate("document.getElementById('stop').click()", True)
                                wait(lambda: evaluate("OperatorUI.snapshot?.state==='stopped'"))
                                wait(lambda: any("hub_delivery_estimate_ms" in s for s in hub.client_samples))
                                first_requests = [r for r in requests if r.session_id == sid]
                                self.assertEqual(" ".join(r.raw_text for r in first_requests).split(), final_words(events))
                                self.assertTrue(any(r.raw_text != r.normalized_text for r in first_requests))
                                self.assertEqual(app.state.operational_run.outcome, "complete")
                                self.assertEqual(eof, [1])
                                samples = [{"session_id": sid, **copy.deepcopy(s)} for s in hub.client_samples]
                                report.update(summarize_pipeline([c for c in captions if c["session_id"] == sid], samples))
                                report["requests"] = [asdict(r) for r in first_requests]
                                report["queue_max"] = hub.translation_queue_max
                                report["first_session_outcome"] = app.state.operational_run.outcome
                                self.assertGreater(report["summary_ms"]["translation_to_paint_estimate_ms"]["n"], 0)
                                # New session must reset sequence, history, watermark and owner state.
                                evaluate("document.getElementById('start').click()", True)
                                wait(lambda: hub.session_id != sid and hub.state == "live")
                                wait(lambda: evaluate("OperatorUI.snapshot?.state==='live' && !document.getElementById('stop').disabled"))
                                wait(lambda: hub.sequence >= 1)
                                self.assertEqual(hub.visual_generation, 0)
                                self.assertTrue(all(c["session_id"] != sid for c in hub.caption_history))
                                evaluate("document.getElementById('stop').click()", True)
                                wait(lambda: evaluate("OperatorUI.snapshot?.state==='stopped'"))
                                self.assertEqual(connections, [1, 2]); self.assertEqual(eof, [1, 2])
                                self.assertEqual(app.state.operational_run.outcome, "complete")
                                self.assertEqual(app.state.operational_run.translator.queue_depth, 0)
                                self.assertTrue(all(size > 0 for _, size in frames))
                                report["second_session_words"] = " ".join(r.raw_text for r in requests if r.session_id != sid)
                    finally:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill(); process.wait(timeout=5)

            with patch("app.translation.engine.provider_from_config", return_value=(
                    FixtureProvider(), TranslationStatus("ready", "release-fixture", "test only"))):
                thread = threading.Thread(target=lambda: server.run(sockets=[bound]), daemon=True)
                thread.start()
                try:
                    # Every browser wait is bounded. Let its finally terminate Chrome
                    # before tearing down ASGI; cancelling to_thread cannot kill it.
                    await asyncio.to_thread(browser)
                finally:
                    server.should_exit = True
                    await asyncio.to_thread(thread.join, 5)
                    bound.close()
                self.assertFalse(thread.is_alive())
            if os.getenv("M8_E2E_OUTPUT"):
                report.update(generated_utc=datetime.now(timezone.utc).isoformat(),
                              scope="AUTOMATED: fake PCM + recorded WLK receive timing + fake provider + real Chrome; not OBS/DeepL/physical speech",
                              fixture_sha256=digest(fixture_path), event_count=len(events))
                Path(os.environ["M8_E2E_OUTPUT"]).write_text(
                    json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

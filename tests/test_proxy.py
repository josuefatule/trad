"""Real WebSocket transport with a local fake WLK; no GPU or audio files."""
import asyncio
import json
from contextlib import nullcontext
import unittest
from types import SimpleNamespace
from pathlib import Path

from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from app.asr.whisperlivekit_client import relay, session_url
from app.main import Settings, create_app
from app.captions.segment_manager import SegmentConfig


class Browser:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = []

    async def receive(self):
        return await self.incoming.get()

    async def send_json(self, data):
        self.outgoing.append(data)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def run_proxy(self, handler, frames, timeout=1, segments=None):
        browser = Browser()
        for frame in frames:
            browser.incoming.put_nowait({"type": "websocket.receive", "bytes": frame})
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = SimpleNamespace(wlk_url=f"ws://127.0.0.1:{port}/asr", language="es",
                                       log_raw=False, connect_timeout=1, stop_timeout=timeout,
                                       segments=segments)
            await relay(browser, settings, "test")
        return browser.outgoing

    async def test_pcm_eof_and_final_snapshot(self):
        received = []

        async def wlk(ws):
            self.assertEqual(ws.request.path, "/asr?mode=full&language=es")
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            async for data in ws:
                received.append(data)
                if not data:
                    payload = {"lines": [{"text": "Hola.", "speaker": 1, "start": "0:00:00.00", "end": "0:00:01.00"}], "buffer_transcription": ""}
                    await ws.send(json.dumps(payload))
                    await ws.send(json.dumps({"type": "ready_to_stop"}))
                    break

        messages = await self.run_proxy(wlk, [b"\x00\x00" * 128, b""])
        self.assertEqual(received, [b"\x00\x00" * 128, b""])
        self.assertEqual(messages[-2]["transcript"]["confirmed_text"], "Hola.")
        self.assertEqual(messages[-1]["state"], "stopped")
        self.assertEqual(messages[-2]["segmentation"]["ready_segments"][0]["reason"], "session_end")
        normalized = messages[-2]["normalization"]["segments"][0]
        self.assertEqual(normalized["raw_text"], "Hola.")
        self.assertEqual(normalized["normalized_text"], "Hola.")

    async def test_ready_segment_is_normalized_without_mutating_raw_text(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            await ws.send(json.dumps({
                "lines": [{"text": "Presión systólica estable.", "speaker": 1,
                           "start": "0:00:00.00", "end": "0:00:01.00"}],
                "buffer_transcription": "",
            }))
            await ws.send(json.dumps({"type": "ready_to_stop"}))

        messages = await self.run_proxy(wlk, [b""])
        final = next(message for message in messages
                     if message["type"] == "asr"
                     and message["segmentation"]["ready_segments"])
        ready = final["segmentation"]["ready_segments"][0]
        normalized = final["normalization"]["segments"][0]
        self.assertEqual(ready["text"], "Presión systólica estable.")
        self.assertEqual(normalized["raw_text"], ready["text"])
        self.assertEqual(normalized["normalized_text"], "Presión sistólica estable.")
        self.assertEqual(normalized["corrections"][0]["rule"], "exact_variant")

    async def test_segmentation_timer_emits_without_asr_updates(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            await ws.send(json.dumps({"lines": [{"text": "Una frase.", "speaker": 1,
                                                "start": "0:00:00.00", "end": "0:00:01.00"}],
                                      "buffer_transcription": ""}))
            await asyncio.sleep(.15)
            await ws.send(json.dumps({"type": "ready_to_stop"}))

        config = SegmentConfig(stabilization_seconds=.03, tick_seconds=.01)
        messages = await self.run_proxy(wlk, [b""], segments=config)
        ticks = [m for m in messages if m["type"] == "segmentation"]
        self.assertEqual(len(ticks), 1)
        self.assertEqual(ticks[0]["segmentation"]["ready_segments"][0]["text"], "Una frase.")
        self.assertEqual(ticks[0]["segmentation"]["pending_segment"], "")
        self.assertEqual(messages[-2]["segmentation"]["ready_segments"], ())

    async def test_reject_non_pcm_server(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": False}))
        with self.assertRaisesRegex(ValueError, "pcm-input"):
            await self.run_proxy(wlk, [])

    async def test_publish_partial_only_changes_with_identical_lines(self):
        # Synthetic protocol snapshots, not presented as observed real speech.
        lines = [{"text": "Confirmado.", "speaker": 1,
                  "start": "0:00:00.00", "end": "0:00:01.00"}]
        partials = ["La", "La hipertensión", "La hipertensión", ""]

        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            for partial in partials:
                await ws.send(json.dumps({"lines": lines, "buffer_transcription": partial}))
            await ws.send(json.dumps({"type": "ready_to_stop"}))

        messages = await self.run_proxy(wlk, [b""])
        snapshots = [m for m in messages if m["type"] == "asr" and "lines" in m["payload"]]
        self.assertEqual([m["transcript"]["partial_text"] for m in snapshots], partials)
        self.assertTrue(all(m["transcript"]["confirmed_text"] == "Confirmado." for m in snapshots))

    async def test_replay_real_voice_payloads_without_losing_fields(self):
        fixture = Path(__file__).parent / "fixtures/wlk_0_2_26_simulstreaming_es_real_voice.json"
        payloads = json.loads(fixture.read_text(encoding="utf-8"))["payloads"]

        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            for payload in payloads:
                await ws.send(json.dumps(payload))
            await ws.send(json.dumps({"type": "ready_to_stop"}))

        messages = await self.run_proxy(wlk, [b""])
        snapshots = [m for m in messages if m["type"] == "asr" and "lines" in m["payload"]]
        self.assertEqual([m["payload"] for m in snapshots], payloads)
        for message in snapshots:
            self.assertEqual(message["transcript"]["partial_text"], "")
            self.assertEqual(message["transcript"]["segments"], message["payload"]["lines"])
            self.assertTrue(message["transcript"]["confirmed_text"])

    async def test_finalization_timeout(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            await ws.wait_closed()
        with self.assertRaisesRegex(TimeoutError, "finalization timed out"):
            await self.run_proxy(wlk, [b""], timeout=.05)

    async def test_upstream_disconnect_is_error(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
        with self.assertRaisesRegex(ConnectionError, "before ready_to_stop"):
            await self.run_proxy(wlk, [])


class HttpTests(unittest.TestCase):
    def test_routes(self):
        with nullcontext("logs/tests") as folder:
            with TestClient(create_app(Settings(log_dir=folder))) as client:
                self.assertEqual(client.get("/health").json()["status"], "ok")
                self.assertIn("LIVE CAPTIONS", client.get("/operator").text)
                self.assertEqual(client.get("/static/operator.js").status_code, 200)

    def test_connection_error_visible(self):
        with nullcontext("logs/tests") as folder:
            settings = Settings(log_dir=folder, wlk_url="ws://127.0.0.1:1/asr", connect_timeout=.1)
            with TestClient(create_app(settings)) as client:
                with client.websocket_connect("/ws/session") as ws:
                    self.assertEqual(ws.receive_json()["state"], "connecting")
                    self.assertEqual(ws.receive_json()["type"], "error")

    def test_full_mode_is_explicit(self):
        self.assertEqual(session_url("ws://localhost:8000/asr?mode=diff&target_language=en", "es"),
                         "ws://localhost:8000/asr?mode=full&language=es")


if __name__ == "__main__":
    unittest.main()

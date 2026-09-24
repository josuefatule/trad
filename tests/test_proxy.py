"""Real WebSocket transport with a local fake WLK; no GPU or audio files."""
import asyncio
import json
from contextlib import nullcontext
import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from app.asr.whisperlivekit_client import relay, session_url
from app.main import Settings, create_app


class Browser:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.outgoing = []

    async def receive(self):
        return await self.incoming.get()

    async def send_json(self, data):
        self.outgoing.append(data)


class ProxyTests(unittest.IsolatedAsyncioTestCase):
    async def run_proxy(self, handler, frames, timeout=1):
        browser = Browser()
        for frame in frames:
            browser.incoming.put_nowait({"type": "websocket.receive", "bytes": frame})
        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = SimpleNamespace(wlk_url=f"ws://127.0.0.1:{port}/asr", language="es",
                                       log_raw=False, connect_timeout=1, stop_timeout=timeout)
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

    async def test_reject_non_pcm_server(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": False}))
        with self.assertRaisesRegex(ValueError, "pcm-input"):
            await self.run_proxy(wlk, [])

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

"""FastAPI WS -> local WLK double -> state -> manager -> client, using real payloads."""
import asyncio
import json
from pathlib import Path
import unittest

from fastapi.testclient import TestClient
from websockets.asyncio.server import serve

from app.captions.segment_manager import SegmentConfig
from app.main import Settings, create_app


class SessionReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_snapshots_pending_eof_and_new_start(self):
        path = Path(__file__).parent / "fixtures/wlk_0_2_26_simulstreaming_es_real_voice.json"
        payloads = json.loads(path.read_text(encoding="utf-8"))["payloads"]

        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            self.assertEqual(await ws.recv(), bytes(256))
            for payload in payloads:
                await ws.send(json.dumps(payload))
            self.assertEqual(await ws.recv(), b"")
            await ws.send(json.dumps({"type": "ready_to_stop"}))
            await ws.wait_closed()

        async with serve(wlk, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(wlk_url=f"ws://127.0.0.1:{port}/asr", log_dir="logs/tests",
                                segments=SegmentConfig(stabilization_seconds=10,
                                                       soft_max_age_seconds=20,
                                                       hard_max_age_seconds=30))

            def browser():
                ids = []
                with TestClient(create_app(settings)) as client:
                    for _ in range(2):
                        with client.websocket_connect("/ws/session") as ws:
                            self.assertEqual(ws.receive_json()["state"], "connecting")
                            self.assertEqual(ws.receive_json()["type"], "config")
                            ws.send_bytes(bytes(256))
                            for payload in payloads:
                                data = ws.receive_json()
                                self.assertEqual(data["payload"], payload)
                                self.assertEqual(data["segmentation"]["ready_segments"], [])
                                self.assertEqual(data["segmentation"]["pending_segment"], payload["lines"][0]["text"].strip())
                            ws.send_bytes(b"")
                            final = ws.receive_json()
                            self.assertEqual(final["payload"]["type"], "ready_to_stop")
                            ready = final["segmentation"]["ready_segments"]
                            self.assertEqual(len(ready), 1)
                            self.assertEqual(ready[0]["reason"], "session_end")
                            self.assertEqual(ready[0]["text"], payloads[-1]["lines"][0]["text"].strip())
                            self.assertEqual(final["segmentation"]["pending_segment"], "")
                            ids.append(ready[0]["id"])
                            self.assertEqual(ws.receive_json()["state"], "stopped")
                            self.assertEqual(ws.receive()["type"], "websocket.close")
                self.assertNotEqual(ids[0], ids[1])

            await asyncio.wait_for(asyncio.to_thread(browser), 10)

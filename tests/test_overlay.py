"""Caption hub, HTTP and single-source WebSocket integration without real DeepL."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tests.operator_client import TestClient
from websockets.asyncio.server import serve

from app.main import Settings, create_app
from app.overlay.config import CaptionConfig
from app.overlay.hub import CaptionHub
from app.translation import TranslationConfig, TranslationResult, TranslatorProvider


def translated(sequence=1, session="a", text="English caption.", provider="deepl", success=True):
    return TranslationResult(session, f"{session}:{sequence}", sequence, "RAW", "NORMALIZED",
                             text if success else None, provider, success,
                             None if success else "SECRET must not be broadcast", 1,
                             0, 0, 0, 0, 0)


class HubTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.
        self.hub = CaptionHub(CaptionConfig(), clock=lambda: self.now)
        self.hub.begin("a")
        self.hub.set_state("a", "live")

    def test_multiple_subscribers_identical_events_order_and_no_duplicates(self):
        first, second = self.hub.subscribe(), self.hub.subscribe()
        first_snapshot, second_snapshot = first.queue.get_nowait(), second.queue.get_nowait()
        self.assertNotEqual(first_snapshot.pop("observer_id"), second_snapshot.pop("observer_id"))
        self.assertEqual(first_snapshot, second_snapshot)
        self.assertTrue(self.hub.publish(translated(1)))
        self.assertFalse(self.hub.publish(translated(1)))
        self.assertTrue(self.hub.publish(translated(2)))
        for expected in (1, 2):
            a, b = first.queue.get_nowait(), second.queue.get_nowait()
            self.assertEqual(a, b)
            self.assertEqual(a["caption"]["sequence"], expected)
            self.assertNotIn("RAW", json.dumps(a))

    def test_gap_rejected_until_predecessor_and_stale_session_rejected(self):
        self.assertFalse(self.hub.publish(translated(2)))
        self.assertTrue(self.hub.publish(translated(1)))
        self.assertTrue(self.hub.publish(translated(2)))
        self.assertFalse(self.hub.publish(translated(3, session="old")))
        self.assertEqual(self.hub.stale_events, 1)

    def test_slow_subscriber_evicted_without_blocking_other_observers(self):
        hub = CaptionHub(CaptionConfig(), queue_size=2)
        hub.begin("a"); hub.set_state("a", "live")
        slow, fast = hub.subscribe(), hub.subscribe()
        fast.queue.get_nowait()
        for sequence in (1, 2, 3):
            hub.publish(translated(sequence))
            self.assertEqual(fast.queue.get_nowait()["caption"]["sequence"], sequence)
        self.assertTrue(slow.closed.is_set())
        self.assertNotIn(slow, hub.subscribers)
        self.assertEqual(hub.broadcast_errors, 1)

    def test_snapshot_atomic_registration_expiry_and_session_reset(self):
        self.hub.config = CaptionConfig(mode="timed_queue")
        self.hub.publish(translated())
        observer = self.hub.subscribe()
        snapshot = observer.queue.get_nowait()
        self.hub.publish(translated(2))
        event = observer.queue.get_nowait()
        self.assertEqual(snapshot["caption"]["sequence"], 1)
        self.assertGreater(event["event_id"], snapshot["event_id"])
        self.now += 7
        self.assertIsNone(self.hub.snapshot()["caption"])
        self.hub.set_state("a", "stopped")
        self.hub.begin("b")
        self.assertEqual(self.hub.sequence, 0)
        self.assertIsNone(self.hub.snapshot()["caption"])
        self.assertFalse(self.hub.publish(translated(3)))

    def test_error_then_next_english_and_mock_filtered(self):
        observer = self.hub.subscribe(); observer.queue.get_nowait()
        self.assertFalse(self.hub.publish(translated(1, success=False)))
        error = observer.queue.get_nowait()
        self.assertEqual(error["state"], "error")
        self.assertNotIn("SECRET", json.dumps(error))
        self.assertTrue(self.hub.publish(translated(2)))
        self.assertFalse(self.hub.publish(translated(3, provider="mock")))
        self.assertFalse(self.hub.publish(translated(4, text="[MOCK EN] hello")))
        self.assertEqual(self.hub.filtered_mock, 2)

    def test_stop_drains_and_disconnect_clears_snapshot(self):
        self.hub.set_state("a", "draining")
        self.assertTrue(self.hub.publish(translated()))
        self.hub.set_state("a", "stopped")
        self.assertIsNotNone(self.hub.snapshot()["caption"])
        self.assertFalse(self.hub.publish(translated(2)))
        self.hub.set_state("a", "disconnected")
        self.assertIsNone(self.hub.snapshot()["caption"])

    def test_single_audio_session_and_subscriber_limit(self):
        with self.assertRaisesRegex(ValueError, "already active"):
            self.hub.begin("b")
        hub = CaptionHub(CaptionConfig(), subscriber_limit=1)
        observer = hub.subscribe()
        with self.assertRaises(ValueError): hub.subscribe()
        hub.unsubscribe(observer)
        self.assertEqual(len(hub.subscribers), 0)

    def test_oversized_caption_and_telemetry_are_instrumented(self):
        self.assertFalse(self.hub.publish(translated(text="x" * 20001)))
        self.assertEqual(self.hub.display_drops, 1)
        self.hub.report_display_drop("a", "queue_overflow", 2)
        self.hub.report_display_drop("old", "queue_overflow", 2)
        self.assertEqual(self.hub.display_drops, 3)


class OverlayRoutesTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(log_dir="logs/tests", translation=TranslationConfig()))

    def test_overlay_preview_transparency_and_safe_config(self):
        with TestClient(self.app) as client:
            page = client.get("/overlay")
            self.assertEqual(page.status_code, 200)
            self.assertIn("caption_renderer.js", page.text)
            self.assertIn("overlay_geometry.js", page.text)
            self.assertIn('id="overlay-canvas"', page.text)
            self.assertNotIn("operator.js", page.text)
            css = client.get("/static/overlay.css").text
            self.assertIn("html, body", css)
            self.assertIn("background: transparent !important", css)
            self.assertNotIn("line-clamp", css)
            self.assertIn("DEMO", client.get("/overlay/preview").text)
            self.assertIn('id="preview-viewport"', client.get("/overlay/preview").text)
            self.assertEqual(client.get("/api/overlay/config?max_lines=1&position=top").json()["position"], "top")
            for query in ("position=javascript:alert(1)", "font_size=9999", "css=body{}",
                          "background_opacity=NaN", "min_display_ms=9000&max_display_ms=1000"):
                self.assertEqual(client.get("/api/overlay/config?" + query).status_code, 400)
            self.assertNotIn("key", json.dumps(client.get("/api/overlay/config").json()).lower())

    def test_caption_region_bounds_and_line_capacity_validation(self):
        with TestClient(self.app) as client:
            config = client.get("/api/overlay/config").json()
            self.assertEqual((config["canvas_width"], config["canvas_height"]), (1920, 1080))
            self.assertEqual((config["region_y"], config["region_height"]), (930, 150))
            self.assertEqual(config["background_opacity"], 0)
            self.assertEqual(config["mode"], "persistent_rolling")
            for query in ("region_y=931", "region_x=1", "region_width=1921",
                          "canvas_height=1000", "region_height=-1", "region_y=NaN",
                          "region_height=60", "padding_y=60", "padding_x=1",
                          "line_height=NaN", "line_height=0.5", "region_width=80&padding_x=32"):
                with self.subTest(query=query):
                    self.assertEqual(client.get("/api/overlay/config?" + query).status_code, 400)
            # Requesting three lines is allowed; frontend reports two fit at 48px.
            self.assertEqual(client.get("/api/overlay/config?max_lines=3").status_code, 200)
            self.assertEqual(client.get("/api/overlay/config?font_size=36").status_code, 200)
            self.assertEqual(client.get("/api/overlay/config?region_y=900&region_height=180").status_code, 200)

    def test_region_settings_from_environment(self):
        with patch.dict("os.environ", {"CAPTION_REGION_Y": "900", "CAPTION_REGION_HEIGHT": "180",
                                       "CAPTION_PADDING_Y": "10", "CAPTION_LINE_HEIGHT": "1.25"}):
            config = CaptionConfig.from_env()
        self.assertEqual((config.region_y, config.region_height, config.padding_y), (900, 180, 10))
        self.assertEqual(config.line_height, 1.25)

    def test_subscription_never_connects_wlk_and_reconnect_snapshot_is_current(self):
        with patch("app.asr.whisperlivekit_client.connect") as connect:
            with TestClient(self.app) as client:
                for _ in range(2):
                    with client.websocket_connect("/ws/overlay") as ws:
                        snapshot = ws.receive_json()
                        self.assertEqual(snapshot["type"], "snapshot")
                        self.assertEqual(snapshot["state"], "waiting")
                        self.assertEqual(client.get("/api/overlay/status").json()["overlay_connections"], 1)
                connect.assert_not_called()

    def test_url_settings_from_environment(self):
        with patch.dict("os.environ", {"CAPTION_MAX_LINES": "3", "CAPTION_POSITION": "center"}):
            config = CaptionConfig.from_env()
        self.assertEqual(config.max_lines, 3)
        self.assertEqual(config.position, "center")
        self.assertEqual(config.with_query({"background_opacity": "0"}).background_opacity, 0)


class OverlayIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_wlk_and_translation_multiple_overlays_then_stop(self):
        upstream_connections = []
        translation_calls = []

        async def wlk(ws):
            upstream_connections.append(ws)
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.recv()
            await ws.send(json.dumps({"lines": [{"text": "Hola.", "speaker": 1}]}))
            await ws.send(json.dumps({"type": "ready_to_stop"}))
            await ws.wait_closed()

        class ControlledProvider(TranslatorProvider):
            name = "test-real-provider"
            async def translate(self, request):
                translation_calls.append(request)
                return "Hello."

        async with serve(wlk, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            settings = Settings(log_dir="logs/tests", wlk_url=f"ws://127.0.0.1:{port}/asr",
                                translation=TranslationConfig(enabled=True, provider="test"))
            from app.translation.engine import TranslationStatus
            with patch("app.translation.engine.provider_from_config", return_value=(
                    ControlledProvider(), TranslationStatus("ready", "test-real-provider", ""))):
                def browser():
                    with TestClient(create_app(settings)) as client:
                        with client.websocket_connect("/ws/overlay") as first, client.websocket_connect("/ws/overlay") as second:
                            self.assertEqual(first.receive_json()["state"], "waiting")
                            second.receive_json()
                            with client.websocket_connect("/ws/session") as operator:
                                self.assertEqual(operator.receive_json()["state"], "connecting")
                                self.assertEqual(operator.receive_json()["capabilities"]["caption_overlay"], 1)
                                operator.send_bytes(b"")
                                english = []
                                while True:
                                    message = operator.receive_json()
                                    if message["type"] == "translation": english.append(message["translation"]["translated_text"])
                                    if message.get("state") == "stopped": break
                                self.assertEqual(english, ["Hello."])
                                self.assertEqual(operator.receive()["type"], "websocket.close")
                            for observer in (first, second):
                                captions = []
                                while True:
                                    message = observer.receive_json()
                                    if message["type"] == "caption": captions.append(message["caption"]["text"])
                                    if message.get("state") == "stopped": break
                                self.assertEqual(captions, ["Hello."])
                            self.assertEqual(client.get("/api/overlay/status").json()["state"], "stopped")
                await asyncio.wait_for(asyncio.to_thread(browser), 10)
        self.assertEqual(len(upstream_connections), 1)
        self.assertEqual(len(translation_calls), 1)

    async def test_operator_disconnect_marks_hub_and_stops_session(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full"}))
            await ws.wait_closed()
        async with serve(wlk, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            app = create_app(Settings(log_dir="logs/tests", wlk_url=f"ws://127.0.0.1:{port}/asr",
                                      translation=TranslationConfig()))
            def browser():
                with TestClient(app) as client, client.websocket_connect("/ws/overlay") as observer:
                    observer.receive_json()
                    with client.websocket_connect("/ws/session") as operator:
                        session = operator.receive_json()["session_id"]
                        operator.receive_json()
                        with client.websocket_connect("/ws/session") as second:
                            rejected = second.receive_json()
                            self.assertEqual(rejected["type"], "error")
                            self.assertEqual(rejected["error_code"], "session_active")
                        self.assertEqual(client.get("/api/overlay/status").json()["session_id"], session)
                        operator.send({"type": "websocket.disconnect", "code": 1000})
                        operator.receive()
                    states = []
                    while "disconnected" not in states:
                        states.append(observer.receive_json().get("state"))
                    self.assertIn("live", states)
            await asyncio.wait_for(asyncio.to_thread(browser), 10)

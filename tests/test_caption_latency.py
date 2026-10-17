import asyncio
from dataclasses import replace
import unittest

from fastapi.testclient import TestClient
from app.main import Settings, create_app
from app.overlay.config import CaptionConfig
from app.overlay.hub import CaptionHub
from app.translation import TranslationConfig, TranslationEngine, TranslatorProvider
from app.translation.timing import TranslationTiming, stage_durations
from tests.test_overlay import translated


class TimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_monotonic_stages_queue_provider_and_publish(self):
        now = [10.]
        hub = CaptionHub(CaptionConfig(), clock=lambda: 100., monotonic_clock=lambda: now[0])
        hub.begin("a"); hub.set_state("a", "live")
        class Provider(TranslatorProvider):
            name = "controlled"
            async def translate(self, request):
                now[0] += .8
                return "English."
        results = []
        async def output(result, snapshot):
            results.append(result)
            now[0] += .01
            hub.record_translation_status("a", snapshot)
            hub.publish(result)
        engine = TranslationEngine(TranslationConfig(enabled=True), Provider(), "a", output,
                                   monotonic_clock=lambda: now[0])
        await engine.start()
        await engine.submit("a:1", "raw", "normalized", timing=TranslationTiming(
            asr_first_seen_mono=5., ready_mono=8.5, normalized_completed_mono=8.6))
        now[0] = 11.
        await engine.wait_idle(); await engine.close()
        durations = hub.last_caption["latency"]
        self.assertEqual(durations["asr_to_ready_ms"], 3500)
        self.assertEqual(durations["ready_to_translation_started_ms"], 2500)
        self.assertEqual(durations["translation_queue_delay_ms"], 1000)
        self.assertEqual(durations["provider_last_attempt_ms"], 800)
        self.assertEqual(durations["translation_to_hub_ms"], 10)
        self.assertEqual(durations["ready_to_hub_ms"], 3310)
        self.assertEqual(results[0].raw_text, "raw")
        self.assertEqual(results[0].normalized_text, "normalized")

    def test_missing_stage_stays_unknown(self):
        self.assertEqual(stage_durations(None, 1), {})
        self.assertIsNone(stage_durations(TranslationTiming(), 1)["asr_to_ready_ms"])


class PersistentHubTests(unittest.TestCase):
    def test_pause_snapshot_history_and_stop_deadline(self):
        now = [100.]
        hub = CaptionHub(CaptionConfig(stop_clear_ms=3000), clock=lambda: now[0])
        hub.begin("a"); hub.set_state("a", "live")
        hub.publish(translated(1, text="First.")); hub.publish(translated(2, text="Second."))
        now[0] += 3600
        self.assertEqual(len(hub.snapshot()["captions"]), 2)
        hub.set_state("a", "stopped"); now[0] += 2
        self.assertEqual(hub.snapshot()["stop_remaining_ms"], 1000)
        self.assertEqual(len(hub.snapshot()["captions"]), 2)
        now[0] += 1
        self.assertEqual(hub.snapshot()["captions"], [])
        hub.begin("b")
        self.assertEqual(list(hub.caption_history), [])

    def test_history_and_telemetry_bounded_and_stale_rejected(self):
        hub = CaptionHub(CaptionConfig())
        hub.begin("a"); hub.set_state("a", "live")
        for index in range(1, 150): hub.publish(translated(index, text="word " * 50))
        self.assertLessEqual(len(hub.caption_history), 128)
        self.assertLessEqual(sum(len(c["text"]) for c in hub.caption_history), 20000)
        subscriber = hub.subscribe()
        sample = {"session_id": "a", "sequence": 149, "renderer_delay_ms": 0,
                  "visual_queue_depth": 0, "visible_caption_count": 3}
        hub.record_client_sample(subscriber, sample)
        self.assertEqual(subscriber.diagnostics["visible_caption_count"], 3)
        hub.record_client_sample(subscriber, {**sample, "session_id": "old", "visible_caption_count": 99})
        self.assertEqual(subscriber.diagnostics["visible_caption_count"], 3)
        hub.record_client_sample(subscriber, {**sample, "renderer_delay_ms": float("nan")})
        self.assertEqual(subscriber.diagnostics["renderer_delay_ms"], 0)
        hub.set_state("a", "disconnected")
        self.assertEqual(hub.snapshot()["captions"], [])
        hub.begin("b")
        self.assertEqual(subscriber.diagnostics, {})

    def test_clock_probe_protocol_without_translation(self):
        app = create_app(Settings(log_dir="logs/tests", translation=TranslationConfig()))
        with TestClient(app) as client, client.websocket_connect("/ws/overlay") as ws:
            self.assertEqual(ws.receive_json()["protocol_version"], 3)
            ws.send_json({"type": "clock_probe", "client_sent_ms": 12.})
            response = ws.receive_json()
            self.assertEqual(response["type"], "clock_sync")
            self.assertEqual(response["client_sent_ms"], 12.)
            self.assertGreaterEqual(response["server_sent_mono_ms"], response["server_received_mono_ms"])
            self.assertEqual(client.get("/api/overlay/config").json()["mode"], "persistent_rolling")
            self.assertEqual(client.get("/api/overlay/config").json()["max_lines"], 3)

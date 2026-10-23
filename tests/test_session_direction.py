"""Bidirectional contract, real local transports; no microphone, GPU or DeepL."""
import asyncio
from dataclasses import replace
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.server import serve

from app.asr.wlk_server import LanguageHandshake, isolated_factory
from app.asr.whisperlivekit_client import relay
from app.captions.identity_normalizer import IdentityNormalizer
from app.captions.terminology_normalizer import TerminologyNormalizer
from app.main import Settings, create_app
from app.session_direction import direction_from_id
from app.translation import TranslationConfig, TranslationEngine
from app.translation.providers import DeepLTranslatorProvider
from tests.test_operator_control import authorize, controlled_relay, headers, local_client
from tests.test_proxy import Browser


class DirectionUnitTests(unittest.TestCase):
    def test_only_explicit_pairs_and_english_exact_identity(self):
        for invalid in (None, "auto", "en-en", "EN-ES", {}, ""):
            with self.assertRaises(ValueError):
                direction_from_id(invalid)
        text = "  systólica — ejection fraction, 5 mg.\nNo edema.  "
        item = IdentityNormalizer().normalize("en:1", text)
        self.assertEqual(item.normalized_text, text)
        self.assertFalse(item.corrections or item.suggestions or item.known_terms)
        spanish = TerminologyNormalizer.from_config().normalize("es:1", "presión arterial systólica")
        self.assertIn("sistólica", spanish.normalized_text)

    def test_wlk_configs_isolated_with_shared_weights_and_rejection(self):
        weights = object()
        shared = SimpleNamespace(cfg=SimpleNamespace(language="es", tokenizer_is_multilingual=True, task="transcribe"), lan="es", shared_model=weights)
        args = SimpleNamespace(backend="faster-whisper", backend_policy="simulstreaming", lan="es")
        factory = isolated_factory(lambda args, asr, language: asr)
        sessions = [factory(args, shared, lang) for lang in ("en", "es", "en")]
        self.assertEqual([s.cfg.language for s in sessions], ["en", "es", "en"])
        self.assertEqual(shared.cfg.language, "es")
        self.assertEqual(len({id(s.cfg) for s in sessions}), 3)
        self.assertTrue(all(s.shared_model is weights for s in sessions))
        for lang in ("auto", "fr", "", "en&language=es"):
            with self.assertRaises(ValueError):
                factory(args, shared, lang)


class DirectionControlTests(unittest.TestCase):
    def test_session_immutable_across_resume_competing_tab_and_closed_gate(self):
        observed = []

        async def inspect(browser, settings, session_id, caption_hub):
            observed.append(settings)
            await controlled_relay(browser, settings, session_id, caption_hub)

        settings = Settings(log_dir="logs/tests", translation=TranslationConfig())
        app = create_app(settings)
        with patch("app.main.relay", inspect), local_client(app) as client:
            boot = client.get("/api/operator/bootstrap").json()
            self.assertEqual(boot["default_direction"], "en-es")
            owner = boot["control_token"]
            other = authorize(client)
            for direction in ("en-es", "es-en"):
                with client.websocket_connect(f"ws://localhost/ws/session?direction={direction}", subprotocols=["operator.v1", owner], headers={"origin": "http://localhost"}) as ws:
                    ws.receive_json(); config = ws.receive_json()
                    sid = config["session_id"]
                    self.assertEqual(config["direction"]["id"], direction)
                    status = client.get("/api/operator/status", headers=headers(owner)).json()
                    self.assertFalse(status["can_change_direction"] or status["can_start"])
                    self.assertTrue(status["session_open"])
                    self.assertEqual(client.post("/api/operator/acknowledge-stop", headers=headers(owner), json={"session_id": sid}).status_code, 409)
                    with client.websocket_connect("ws://localhost/ws/session?direction=es-en", subprotocols=["operator.v1", other], headers={"origin": "http://localhost"}) as rival:
                        self.assertEqual(rival.receive_json()["type"], "error")
                    resumed = client.post("/api/operator/resume", headers=headers(owner), json={"resume_secret": boot["resume_secret"]}).json()
                    old = owner; owner = resumed["control_token"]; boot = resumed
                    self.assertEqual(client.get("/api/operator/status", headers=headers(old)).status_code, 403)
                    state = client.get("/api/operator/status", headers=headers(owner)).json()
                    self.assertTrue(state["owns_session"])
                    self.assertEqual(state["direction"]["id"], direction)
                    ws.send_bytes(b"")
                    self.assertEqual(ws.receive_json()["state"], "stopped")
                self.assertTrue(client.get("/api/operator/status", headers=headers(owner)).json()["can_change_direction"])
            self.assertEqual([s.language for s in observed], ["en", "es"])
            self.assertEqual([(s.translation.source_language, s.translation.target_language) for s in observed], [("en", "es"), ("es", "en")])
            self.assertEqual(settings.language, "es")
            self.assertEqual(settings.translation.source_language, "es")

    def test_invalid_direction_and_incomplete_closure_require_owner_ack(self):
        app = create_app(Settings(log_dir="logs/tests", translation=TranslationConfig()))

        async def failure(browser, settings, session_id, caption_hub):
            raise ConnectionError("injected transport failure")

        with patch("app.main.relay", failure), local_client(app) as client:
            owner = authorize(client); other = authorize(client)
            for query in ("direction=auto", "direction=en-es&direction=es-en", "direction="):
                with self.assertRaises(WebSocketDisconnect) as rejected:
                    with client.websocket_connect("ws://localhost/ws/session?" + query, subprotocols=["operator.v1", owner], headers={"origin": "http://localhost"}):
                        pass
                self.assertEqual(rejected.exception.code, 4400)
            with client.websocket_connect("ws://localhost/ws/session?direction=en-es", subprotocols=["operator.v1", owner], headers={"origin": "http://localhost"}) as ws:
                self.assertEqual(ws.receive_json()["type"], "error")
            status = client.get("/api/operator/status", headers=headers(owner)).json()
            self.assertTrue(status["requires_stop_acknowledgement"])
            self.assertFalse(status["can_start"] or status["can_change_direction"])
            body = {"session_id": status["session_id"]}
            self.assertEqual(client.post("/api/operator/acknowledge-stop", headers=headers(other), json=body).status_code, 403)
            self.assertEqual(client.post("/api/operator/acknowledge-stop", headers=headers(owner), json={"session_id": "stale"}).status_code, 409)
            self.assertEqual(client.post("/api/operator/acknowledge-stop", headers=headers(owner), json=body).status_code, 200)
            status = client.get("/api/operator/status", headers=headers(owner)).json()
            self.assertTrue(status["can_change_direction"])
            self.assertEqual(status["reliability"]["outcome"], "incomplete")


class DirectionTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_unattested_or_wrong_wlk_language_rejected_before_pcm(self):
        for config in ({}, {"session_language_isolation": 1, "session_language": "es"}):
            frames = []
            async def wlk(ws):
                await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full", **config}))
                async for pcm in ws: frames.append(pcm)
            async with serve(wlk, "127.0.0.1", 0) as server:
                settings = Settings(log_dir="logs/tests", language="en", require_language_ack=True,
                    wlk_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr", translation=TranslationConfig())
                browser = Browser()
                browser.incoming.put_nowait({"type": "websocket.receive", "bytes": b"\0\0"})
                with self.assertRaisesRegex(ValueError, "language isolation"):
                    await relay(browser, settings, "attestation")
                self.assertFalse(frames)

    async def test_language_handshake_rejects_invalid_and_attests_config(self):
        async def app(scope, receive, send):
            await send({"type": "websocket.send", "text": json.dumps({"type": "config"})})
        middleware = LanguageHandshake(app)
        for query in (b"language=en", b"language=es"):
            messages = []
            async def send(message): messages.append(message)
            await middleware({"type": "websocket", "path": "/asr", "query_string": query}, None, send)
            self.assertEqual(json.loads(messages[0]["text"])["session_language_isolation"], 1)
        for query in (b"", b"language=auto", b"language=en&language=es"):
            messages = []
            await middleware({"type": "websocket", "path": "/asr", "query_string": query}, None, send)
            self.assertEqual(messages[0]["code"], 4400)

    async def test_alternating_pipeline_deepl_body_context_clear_overlay_and_stop(self):
        requests, bodies, paths = [], [], []

        class Response:
            def __init__(self, text): self.text = text
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return json.dumps({"translations": [{"text": self.text}]}).encode()

        def opener(req, timeout):
            body = json.loads(req.data); bodies.append(body)
            return Response("Traducción española." if body["target_lang"] == "ES" else "English translation.")

        class RecordingDeepL(DeepLTranslatorProvider):
            async def translate(self, request):
                requests.append(request)
                return await super().translate(request)

        def engine(config, sid, callback):
            return TranslationEngine(config, RecordingDeepL("test-only", opener=opener), sid, callback)

        async def wlk(ws):
            paths.append(ws.request.path)
            lang = parse_qs(urlsplit(ws.request.path).query)["language"][0]
            await ws.send(json.dumps({"type": "config", "useAudioWorklet": True, "mode": "full", "session_language": lang, "session_language_isolation": 1}))
            lines = []
            async for pcm in ws:
                if not pcm:
                    await ws.send('{"type":"ready_to_stop"}')
                    return
                text = "English systólica: no edema, 5 mg." if lang == "en" else "Presión arterial systólica y diastólica."
                lines.append({"text": text, "speaker": 1})
                await ws.send(json.dumps({"lines": lines, "buffer_transcription": ""}))

        async with serve(wlk, "127.0.0.1", 0) as upstream:
            settings = Settings(log_dir="logs/tests", wlk_url=f"ws://127.0.0.1:{upstream.sockets[0].getsockname()[1]}/asr", translation=TranslationConfig(enabled=True, provider="deepl"))
            app = create_app(settings)

            def operate():
                with local_client(app) as client:
                    owner = authorize(client)
                    for direction in ("en-es", "es-en", "en-es"):
                        with client.websocket_connect(f"ws://localhost/ws/session?direction={direction}", subprotocols=["operator.v1", owner], headers={"origin": "http://localhost"}) as ws:
                            ws.receive_json(); config = ws.receive_json()
                            self.assertEqual(config["direction"]["id"], direction)
                            # Snapshot after START is empty, including across reversed sessions.
                            with client.websocket_connect("ws://localhost/ws/overlay") as overlay:
                                snap = overlay.receive_json()
                                self.assertFalse(snap["captions"])
                                sid = config["session_id"]
                            messages = []
                            for number in range(2):
                                ws.send_bytes(b"\0\0")
                                while True:
                                    msg = ws.receive_json(); messages.append(msg)
                                    if msg["type"] == "translation": break
                                if number == 0:
                                    self.assertEqual(client.post("/api/operator/clear", headers=headers(owner), json={"protocol_version": 1, "session_id": sid, "visual_generation": 0}).status_code, 200)
                                    with client.websocket_connect("ws://localhost/ws/overlay") as overlay:
                                        self.assertFalse(overlay.receive_json()["captions"])
                            ws.send_bytes(b"")
                            while True:
                                msg = ws.receive_json(); messages.append(msg)
                                if msg.get("state") == "stopped": break
                            translated = [m["translation"] for m in messages if m["type"] == "translation"]
                            self.assertTrue(translated)
                            self.assertEqual(len({t["sequence"] for t in translated}), len(translated))
                            pair = direction_from_id(direction)
                            self.assertTrue(all((t["source_language"], t["target_language"]) == (pair.source_language, pair.target_language) for t in translated))
                            with client.websocket_connect("ws://localhost/ws/overlay") as overlay:
                                snap = overlay.receive_json()
                                self.assertEqual(snap["direction"]["id"], direction)
                                self.assertTrue(all(c["target_language"] == pair.target_language for c in snap["captions"]))
                        self.assertEqual(client.get("/api/operator/status", headers=headers(owner)).json()["reliability"]["outcome"], "complete")
                        deadline = time.monotonic() + 2
                        while not client.get("/api/operator/status", headers=headers(owner)).json()["can_start"]:
                            self.assertLess(time.monotonic(), deadline, "Previous transport did not finish closing")
                            time.sleep(.01)

            with patch("app.asr.whisperlivekit_client.build_translation_engine", engine):
                await asyncio.wait_for(asyncio.to_thread(operate), 20)
        self.assertEqual([parse_qs(urlsplit(p).query)["language"][0] for p in paths], ["en", "es", "en"])
        sessions = list(dict.fromkeys(r.session_id for r in requests))
        self.assertEqual(len(sessions), 3)
        for sid in sessions:
            group = [r for r in requests if r.session_id == sid]
            self.assertFalse(group[0].context_segments)
            self.assertTrue(group[-1].context_segments)
            self.assertTrue(all(c.segment_id.startswith(sid) for r in group for c in r.context_segments))
        self.assertTrue(all(r.raw_text == r.normalized_text for r in requests if r.source_language == "en"))
        self.assertTrue(any("sistólica" in r.normalized_text for r in requests if r.source_language == "es"))
        self.assertEqual({(b["source_lang"], b["target_lang"]) for b in bodies}, {("EN", "ES"), ("ES", "EN")})
        self.assertTrue(any("context" in b for b in bodies))

"""M7 fault injection. No external WLK, microphone, Internet or billable calls."""
import asyncio
from dataclasses import replace
import io
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, patch
from urllib.error import HTTPError

from fastapi import WebSocketDisconnect
from app.asr.whisperlivekit_client import starting_connection, relay
from app.main import Settings, create_app
from app.operator_control import OperatorAuthority, OperatorBrowser
from app.reliability import OperationalRun, ReliabilityConfig, SafeLogFilter, backoff
from app.translation import TranslationConfig, TranslationEngine, MockTranslatorProvider
from app.translation.timing import TranslationTiming
from tests.test_operator_control import local_client, headers, controlled_relay
from tests.test_overlay import translated
from tests.test_proxy import Browser
from app.overlay.hub import CaptionHub
from app.overlay.config import CaptionConfig


class Clock:
    def __init__(self):self.now=100.
    def __call__(self):return self.now
    async def sleep(self,seconds):self.now+=seconds;await asyncio.sleep(0)


class ReliabilityHealthTests(unittest.TestCase):
    def setUp(self):
        self.clock=Clock();self.run=OperationalRun(clock=self.clock);self.run.reset("a")
        self.hub=CaptionHub(CaptionConfig());self.hub.begin("a");self.hub.set_state("a","live")
        self.hub.subscribe()

    def test_real_frames_not_open_socket_and_signal_without_asr(self):
        self.clock.now+=20
        health=self.run.health(self.hub,0)
        self.assertIn("audio_frames_missing",health["reason"])
        self.run.audio(b"\x00\x10"*320)
        health=self.run.health(self.hub,0)
        self.assertNotIn("audio_frames_missing",health["reason"])
        self.assertIn("asr_messages_missing",health["reason"])
        self.run.asr({"lines":[],"buffer_transcription":""})
        self.assertEqual(self.run.health(self.hub,0)["state"],"READY")

    def test_prolonged_speaker_silence_is_not_capture_or_asr_failure(self):
        for _ in range(240):
            self.clock.now+=1;self.run.audio(b"\x00\x00"*320)
            h=self.run.health(self.hub,0)
            self.assertNotIn("missing",h["reason"])
        self.assertTrue(h["components"]["asr"]["silence_or_unverified"])
        self.assertEqual(h["audio_frames"],240)

    def test_owner_loss_no_takeover_and_visible_overlay_absence(self):
        h=self.run.health(self.hub,16)
        self.assertIn("operator_owner_missing",h["reason"])
        for s in tuple(self.hub.subscribers):self.hub.unsubscribe(s)
        self.assertIn("overlay_no_subscribers",self.run.health(self.hub,16)["reason"])

    def test_journal_bounds_gap_and_ui_tail_counted(self):
        r=OperationalRun(replace(ReliabilityConfig(),journal_events=3,ui_transcript_characters=10))
        for i in range(10):r.append({"type":"translation","translation":{"sequence":i+1}})
        self.assertEqual((len(r.journal),r.truncated_events),(3,7))
        r.retain({"type":"asr","transcript":{"confirmed_text":"x"*30,"partial_text":""}})
        history=r.journal_snapshot(0)
        self.assertTrue(history["history_gap"])
        self.assertEqual(history["first_translation_sequence"],8)
        self.assertEqual(history["transcript"]["history_truncated_characters"],20)
        self.assertEqual(len(history["transcript"]["confirmed_text"]),10)

    def test_journal_byte_budget_and_oversized_gap_are_explicit(self):
        r=OperationalRun(replace(ReliabilityConfig(),journal_max_bytes=200))
        for i in range(10):r.append({"type":"example","text":"x"*50})
        self.assertLessEqual(r.journal_bytes,200);self.assertGreater(r.truncated_events,0)
        r.append({"type":"example","text":"x"*1000})
        self.assertTrue(r.journal_snapshot(r.cursor-1)["history_gap"])
        self.assertEqual(r.journal_snapshot(r.cursor)["events"],[])
        future=r.journal_snapshot(999)
        self.assertTrue(future["history_gap"]);self.assertEqual(future["events"],list(r.journal))

    def test_metadata_logs_redact_content_credentials_and_exceptions(self):
        stream=io.StringIO();handler=logging.StreamHandler(stream)
        handler.addFilter(SafeLogFilter(lambda:("PRIVATE_KEY","PRIVATE_TOKEN")))
        log=logging.Logger("test");log.addHandler(handler)
        log.info('segment_ready %s',json.dumps({"text":"CONFIDENTIAL MEDICAL TEXT","id":"s:1"}))
        log.info('session=abc provider error=PRIVATE_KEY PRIVATE_TOKEN private exception')
        log.info('Authorization: PRIVATE_KEY')
        try:raise ValueError("CONFIDENTIAL MEDICAL TEXT PRIVATE_KEY")
        except ValueError:log.exception("provider failed")
        result=stream.getvalue()
        for secret in ("CONFIDENTIAL","PRIVATE_KEY","PRIVATE_TOKEN","private exception","Traceback"):
            self.assertNotIn(secret,result)
        self.assertIn("text_characters",result);self.assertIn("exception_type=ValueError",result)

    def test_config_validation_and_backoff_bounds(self):
        for name in ("connect_attempts","max_session_seconds","audio_stale_seconds"):
            with self.assertRaises(ValueError):ReliabilityConfig(**{name:0})
        self.assertEqual(backoff(0,1,4,0),.75)
        self.assertEqual(backoff(9,1,4,1),4)


class StartupRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):return SimpleNamespace(connect_timeout=.1,reliability=ReliabilityConfig())

    async def test_wlk_startup_recovers_once_before_any_pcm(self):
        upstream=SimpleNamespace(recv=AsyncMock(return_value='{"type":"config","useAudioWorklet":true,"mode":"full"}'),close=AsyncMock())
        clock=Clock();r=OperationalRun(clock=clock);r.reset("a")
        with patch("app.asr.whisperlivekit_client.connect",AsyncMock(side_effect=[OSError(),upstream])) as connect:
            async with starting_connection("ws://local",self.settings(),AsyncMock(),json.loads,r,clock.sleep) as (ws,config):
                self.assertIs(ws,upstream)
            self.assertEqual(connect.await_count,2);self.assertEqual(r.counters["wlk_reconnect_attempts"],1)
        upstream.close.assert_awaited_once()

    async def test_repeated_startup_failure_is_bounded(self):
        clock=Clock();send=AsyncMock()
        with patch("app.asr.whisperlivekit_client.connect",AsyncMock(side_effect=OSError())) as connect:
            with self.assertRaisesRegex(ConnectionError,"exhausted"):
                async with starting_connection("ws://local",self.settings(),send,json.loads,sleep=clock.sleep):pass
            self.assertEqual(connect.await_count,3);self.assertEqual(send.await_count,2)
        self.assertLess(clock.now-100,1.6)

    async def test_live_failure_never_reconnects_and_cancellation_closes(self):
        upstream=SimpleNamespace(recv=AsyncMock(return_value='{"type":"config","useAudioWorklet":true,"mode":"full"}'),close=AsyncMock())
        with patch("app.asr.whisperlivekit_client.connect",AsyncMock(return_value=upstream)) as connect:
            with self.assertRaisesRegex(ConnectionError,"LIVE"):
                async with starting_connection("ws://local",self.settings(),AsyncMock(),json.loads):raise ConnectionError("LIVE lost PCM")
            self.assertEqual(connect.await_count,1)
            with self.assertRaises(asyncio.CancelledError):
                async with starting_connection("ws://local",self.settings(),AsyncMock(),json.loads):raise asyncio.CancelledError()
        self.assertEqual(upstream.close.await_count,2)

    async def test_cancel_backoff_has_no_second_connection(self):
        waiting=asyncio.Event()
        async def sleep(_):waiting.set();await asyncio.Future()
        async def run():
            async with starting_connection("ws://local",self.settings(),AsyncMock(),json.loads,sleep=sleep):pass
        with patch("app.asr.whisperlivekit_client.connect",AsyncMock(side_effect=OSError())) as connect:
            task=asyncio.create_task(run());await waiting.wait();task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            self.assertEqual(connect.await_count,1)


class OperatorRecoveryTests(unittest.TestCase):
    def setUp(self):self.app=create_app(Settings(log_dir="logs/tests",translation=TranslationConfig()))

    def test_observer_recovery_metrics_validated_once_without_control_authority(self):
        hub=self.app.state.caption_hub;hub.begin("a");hub.set_state("a","live")
        with local_client(self.app) as client:
            token=client.get("/api/operator/bootstrap").json()["control_token"]
            with client.websocket_connect("ws://localhost/ws/overlay") as ws:
                ws.receive_json()
                ws.send_json({"type":"connection_health","session_id":"a","attempts":21,"downtime_ms":300})
                ws.send_json({"type":"connection_health","session_id":"a","attempts":2,"downtime_ms":300})
                ws.send_json({"type":"connection_health","session_id":"a","attempts":20,"downtime_ms":999})
                ws.send_json({"type":"clock_probe","client_sent_ms":1})
                self.assertEqual(ws.receive_json()["type"],"clock_sync")
                response=client.get("/api/operator/status",headers=headers(token))
                self.assertEqual(response.headers["cache-control"],"no-store")
                data=response.json();transport=data["latency_diagnostics"]["observers"][0]["transport"]
                self.assertEqual(transport["client_reconnect_attempts"],2)
                self.assertEqual(data["reliability"]["counters"]["overlay_client_reconnect_attempts"],2)
                self.assertFalse(data["owns_session"])

    def test_refresh_rotates_owner_preserves_capture_and_stop_is_idempotent(self):
        calls=[]
        async def record(*args,**kwargs):calls.append(1);await controlled_relay(*args,**kwargs)
        with patch("app.main.relay",record),local_client(self.app) as client:
            boot=client.get("/api/operator/bootstrap").json();old=boot["control_token"]
            with client.websocket_connect("ws://localhost/ws/session",subprotocols=["operator.v1",old],headers={"origin":"http://localhost"}) as capture:
                sid=capture.receive_json()["session_id"];capture.receive_json()
                capture.send_bytes(b"\x00\x00"*320)
                resumed=client.post("/api/operator/resume",headers=headers(old),json={"resume_secret":boot["resume_secret"]})
                self.assertEqual(resumed.status_code,200);new=resumed.json()["control_token"]
                status=client.get("/api/operator/status",headers=headers(new)).json()
                self.assertTrue(status["owns_session"]);self.assertEqual(status["session_id"],sid)
                self.assertEqual(calls,[1]);self.assertEqual(status["state"],"live")
                self.assertEqual(client.get("/api/operator/status",headers=headers(old)).status_code,403)
                self.assertEqual(client.post("/api/operator/resume",headers=headers(old),json={"resume_secret":boot["resume_secret"]}).status_code,403)
                body={"session_id":sid}
                self.assertTrue(client.post("/api/operator/stop",headers=headers(new),json=body).json()["requested"])
                self.assertFalse(client.post("/api/operator/stop",headers=headers(new),json=body).json()["requested"])
                self.assertEqual(capture.receive_json()["command"],"stop")
                capture.send_bytes(b"");self.assertEqual(capture.receive_json()["state"],"stopped")

    def test_authorized_admin_only_after_lease_lost_and_old_owner_revoked(self):
        with patch("app.main.relay",controlled_relay),local_client(self.app) as client:
            boot=client.get("/api/operator/bootstrap").json();old=boot["control_token"]
            other=client.get("/api/operator/bootstrap").json()["control_token"]
            code=json.loads((Path(".runtime")/f"operator-{os.getpid()}.json").read_text())["code"]
            with client.websocket_connect("ws://localhost/ws/session",subprotocols=["operator.v1",old],headers={"origin":"http://localhost"}) as ws:
                sid=ws.receive_json()["session_id"];ws.receive_json()
                body={"session_id":sid,"admin_code":code}
                self.assertEqual(client.post("/api/operator/recover",headers=headers(other),json=body).status_code,409)
                self.app.state.operator_authority.owner_seen=time.monotonic()-16
                self.assertEqual(client.post("/api/operator/recover",headers=headers(other),json={**body,"admin_code":"wrong"}).status_code,403)
                self.assertEqual(client.post("/api/operator/recover",headers={**headers(other),"origin":"http://evil.example"},json=body).status_code,403)
                self.assertEqual(client.post("/api/operator/recover",headers=headers(other),json=body).status_code,200)
                self.assertEqual(client.get("/api/operator/status",headers=headers(old)).status_code,403)
                self.assertTrue(client.get("/api/operator/status",headers=headers(other)).json()["owns_session"])
                self.assertNotEqual(json.loads((Path(".runtime")/f"operator-{os.getpid()}.json").read_text())["code"],code)
                ws.send_bytes(b"");self.assertEqual(ws.receive_json()["state"],"stopped")

    def test_resume_secret_and_admin_control_require_local_origin_nonce(self):
        with local_client(self.app) as client:
            boot=client.get("/api/operator/bootstrap").json();token=boot["control_token"]
            self.assertEqual(client.post("/api/operator/resume",headers=headers(token),json={"resume_secret":"wrong"}).status_code,403)
            self.assertEqual(client.post("/api/operator/resume",headers=headers(token),json={"resume_secret":"inválido"}).status_code,403)
            for path in ("resume","recover","stop","translator-reset"):
                self.assertEqual(client.post("/api/operator/"+path,json={}).status_code,403)
                self.assertEqual(client.post("/api/operator/"+path,headers={**headers(token),"host":"evil.example"},json={}).status_code,403)

    def test_recovery_at_full_tab_budget_does_not_create_unbounded_tokens(self):
        auth=OperatorAuthority();tokens=[auth.issue() for _ in range(64)]
        old=tokens[0];new=auth.resume(old,auth.resume_secrets[old])
        self.assertEqual(len(auth.tokens),64);self.assertEqual(len(auth.resume_secrets),64)
        self.assertTrue(auth.valid(new));self.assertFalse(auth.valid(old))


class ProviderFaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_http_keeps_single_admission_until_socket_finishes(self):
        import threading
        from app.translation.providers import DeepLTranslatorProvider,ProviderBusyError
        from app.translation.models import TranslationRequest
        entered=threading.Event();release=threading.Event();finished=threading.Event();calls=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*_):finished.set()
            def read(self,limit):return b'{"translations":[{"text":"OK"}]}'
        def opener(request,timeout):
            calls.append(1);entered.set();release.wait(1);return Response()
        provider=DeepLTranslatorProvider("test-only",request_timeout=.5,opener=opener)
        request=TranslationRequest("a","a:1",1,"R","N",(),"es","en",0)
        task=asyncio.create_task(provider.translate(request))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait,.5))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):await task
            with self.assertRaises(ProviderBusyError):await provider.translate(request)
            self.assertEqual(len(calls),1)
        finally:
            release.set();await asyncio.to_thread(finished.wait,1);await asyncio.sleep(.01)
        self.assertEqual(await provider.translate(request),"OK")

    async def engine(self,actions,**options):
        clock=Clock();results=[]
        class Provider:
            name="fault-test"
            def __init__(self):self.calls=0
            async def translate(self,request):
                item=actions[self.calls];self.calls+=1
                if item=="timeout":raise TimeoutError()
                if isinstance(item,Exception):raise item
                return item
        async def collect(result,_):results.append(result)
        engine=TranslationEngine(TranslationConfig(enabled=True,provider="test",**options),Provider(),"a",collect,monotonic_clock=clock,sleep=clock.sleep)
        await engine.start();self.addAsyncCleanup(engine.close)
        return engine,clock,results

    async def test_timeout_and_temporary_internet_backoff_order_and_billing_risk(self):
        for failure in ("timeout",OSError("private network detail")):
            engine,clock,results=await self.engine([failure,"OK","NEXT"])
            await engine.submit("a:1","RAW","NORMALIZED");await engine.submit("a:2","RAW2","NORMALIZED2")
            await engine.wait_idle()
            self.assertEqual([r.translated_text for r in results],["OK","NEXT"])
            self.assertEqual(engine.metrics.retries,1);self.assertEqual(engine.metrics.possible_duplicate_requests,1)
            self.assertGreater(clock.now,100);self.assertEqual(engine.health,"READY")

    async def test_429_respects_retry_after_and_total_deadline(self):
        error=HTTPError("https://fake",429,"private",{"Retry-After":"2"},None)
        engine,clock,results=await self.engine([error,"OK"])
        first=await engine.submit("a:1","R","N");await engine.wait_idle()
        self.assertEqual(engine.provider.calls,2);self.assertEqual(clock.now,102)
        engine,clock,results=await self.engine([error],request_deadline_seconds=1)
        await engine.submit("a:1","R","N");await engine.submit("a:2","R","N");await engine.wait_idle()
        self.assertEqual(engine.provider.calls,1);self.assertFalse(any(r.success for r in results))
        self.assertEqual(results[1].error,"provider_cooldown")

    async def test_final_429_attempt_also_blocks_next_request_until_retry_after(self):
        engine,clock,results=await self.engine([HTTPError("https://fake",429,"",{"Retry-After":"5"},None)],retries=0)
        await engine.submit("a:1","R","N");await engine.submit("a:2","R","N");await engine.wait_idle()
        self.assertEqual(engine.provider.calls,1);self.assertEqual(results[1].error,"provider_cooldown")
        self.assertEqual(engine.snapshot()["cooldown_remaining_seconds"],5)

    async def test_result_delivery_failure_is_visible_even_if_provider_succeeded(self):
        engine,_,results=await self.engine(["OK"])
        async def broken(*_):raise ConnectionError("controlled result transport failure")
        engine.on_result=broken
        with self.assertLogs("captions",level="ERROR"):
            await engine.submit("a:1","R","N");await engine.wait_idle()
        self.assertEqual(engine.metrics.successes,1);self.assertEqual(engine.metrics.delivery_failures,1)
        self.assertEqual(engine.snapshot()["health"],"DEGRADED")

    async def test_auth_and_quota_latch_until_explicit_rearm(self):
        for code in (401,403,456):
            engine,_,results=await self.engine([HTTPError("https://fake",code,"SECRET",{},None),"rearmed"])
            await engine.submit("a:1","R","N");await engine.submit("a:2","R","N");await engine.wait_idle()
            self.assertEqual(engine.provider.calls,1);self.assertEqual(engine.metrics.permanent_errors,1)
            self.assertEqual(engine.health,"ERROR");self.assertEqual([r.sequence for r in results],[1,2])
            engine.rearm();await engine.submit("a:3","R","N");await engine.wait_idle()
            self.assertEqual(results[-1].translated_text,"rearmed")

    async def test_500_retry_empty_response_and_queue_expiry(self):
        engine,clock,results=await self.engine([HTTPError("https://fake",503,"",{},None),"OK",""])
        first=await engine.submit("a:1","R","N");await engine.wait_idle()
        await engine.submit("a:2","R","N");await engine.wait_idle()
        self.assertEqual(engine.provider.calls,3);self.assertEqual(results[-1].error,"provider_invalid_response")
        request=replace(first,timing=TranslationTiming(queued_mono=0))
        result=await engine._translate(request)
        self.assertEqual(result.error,"translation_queue_expired");self.assertEqual(result.attempt_count,0)

    async def test_completed_results_and_context_zero_are_bounded_under_saturation(self):
        class Blocked:
            name="blocked"
            async def translate(self,_):await asyncio.Future()
        engine=TranslationEngine(TranslationConfig(enabled=True,provider="test",context_segments=0,queue_maxsize=1,max_pending_results=8),Blocked(),"a")
        await engine.start()
        for i in range(8):await engine.submit(str(i),"R","N")
        with self.assertRaisesRegex(RuntimeError,"budget"):await engine.submit("overflow","R","N")
        self.assertLessEqual(len(engine._completed),8);self.assertEqual(len(engine._context),0)
        await engine.close()
        self.assertEqual(engine.metrics.cancelled,8);self.assertEqual(engine.queue_depth,0)
        self.assertFalse(engine._workers);self.assertFalse(engine._completed)

    async def test_out_of_order_completion_is_emitted_once_and_old_generation_rejected(self):
        engine,_,results=await self.engine(["unused"])
        from app.translation.models import TranslationRequest
        request=TranslationRequest("a","a:1",1,"R","N",(),"es","en",0)
        one=engine._failure(request,"test",0,0,0);two=replace(one,sequence=2,segment_id="a:2")
        await engine._store_result(two,0);self.assertEqual(results,[])
        await engine._store_result(one,0);self.assertEqual([r.sequence for r in results],[1,2])
        await engine.reset("b");await engine._store_result(one,0)
        self.assertEqual(engine.metrics.stale_discarded,1)
        self.assertEqual([r.session_id for r in results],["a","a"])


class StopFaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_character_budget_stops_before_billable_submission(self):
        from websockets.asyncio.server import serve
        async def wlk(ws):
            await ws.send('{"type":"config","useAudioWorklet":true,"mode":"full"}')
            await ws.send('{"lines":[{"speaker":1,"text":"Texto confirmado final."}]}')
            await ws.wait_closed()
        r=OperationalRun(replace(ReliabilityConfig(),max_ready_characters=10));r.reset("a")
        raw=Browser();adapter=OperatorBrowser(raw,"a",r)
        async with serve(wlk,"127.0.0.1",0) as server:
            settings=Settings(wlk_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr",reliability=r.config,
                              translation=TranslationConfig(enabled=True,provider="mock"))
            with self.assertRaisesRegex(RuntimeError,"READY history budget"):await asyncio.wait_for(relay(adapter,settings,"a"),2)
        self.assertEqual(r.translator.provider.requests,[])
        self.assertGreater(r.ready_characters,10);self.assertFalse(r.translator._workers)

    async def test_unexpected_wlk_final_without_capture_eof_is_never_complete(self):
        from websockets.asyncio.server import serve
        async def wlk(ws):
            await ws.send('{"type":"config","useAudioWorklet":true,"mode":"full"}')
            await ws.send('{"type":"ready_to_stop"}')
            await ws.wait_closed()
        r=OperationalRun();r.reset("a");raw=Browser();adapter=OperatorBrowser(raw,"a",r)
        async with serve(wlk,"127.0.0.1",0) as server:
            settings=Settings(wlk_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr",translation=TranslationConfig())
            with self.assertRaisesRegex(ConnectionError,"before audio EOF"):await relay(adapter,settings,"a")
        self.assertFalse(any(message.get("state")=="stopped" for message in raw.outgoing))
        self.assertFalse(r.translator._workers)

    async def test_asr_budget_rejects_payload_before_normalization_or_translation(self):
        from websockets.asyncio.server import serve
        async def wlk(ws):
            await ws.send('{"type":"config","useAudioWorklet":true,"mode":"full"}')
            await ws.send(json.dumps({"lines":[{"speaker":1,"text":"x"*50}]}))
            await ws.wait_closed()
        r=OperationalRun(replace(ReliabilityConfig(),max_asr_characters=20));r.reset("a")
        raw=Browser();adapter=OperatorBrowser(raw,"a",r)
        async with serve(wlk,"127.0.0.1",0) as server:
            settings=Settings(wlk_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr",reliability=r.config,
                              translation=TranslationConfig(enabled=True,provider="mock"))
            with self.assertRaisesRegex(RuntimeError,"history budget"):
                await relay(adapter,settings,"a")
        self.assertEqual(r.translator.provider.requests,[])
        self.assertEqual(r.ready_count,0);self.assertEqual(r.translator.queue_depth,0)

    async def test_capture_no_flush_forces_eof_and_incomplete_including_continuous_frames(self):
        clock=Clock();r=OperationalRun(clock=clock);r.reset("a");r.stop_requested_at=90
        socket=SimpleNamespace(receive=AsyncMock(return_value={"type":"websocket.receive","bytes":b"\x00\x00"}))
        data=await OperatorBrowser(socket,"a",r).receive()
        self.assertEqual(data["bytes"],b"");self.assertEqual(r.counters["forced_audio_eof"],1)
        socket.receive.assert_not_called()
        r.retain({"type":"status","state":"stopped"});self.assertEqual(r.outcome,"incomplete")

    async def test_stop_waiting_on_provider_is_bounded_and_releases_tasks(self):
        from websockets.asyncio.server import serve
        async def wlk(ws):
            await ws.send(json.dumps({"type":"config","useAudioWorklet":True,"mode":"full"}))
            await ws.recv()
            await ws.send(json.dumps({"lines":[{"speaker":1,"text":"Texto final pendiente."}]}))
            await ws.send('{"type":"ready_to_stop"}')
            await ws.wait_closed()
        class Blocked:
            name="blocked"
            async def translate(self,_):await asyncio.Future()
        from app.translation.engine import TranslationStatus
        async with serve(wlk,"127.0.0.1",0) as server:
            settings=Settings(wlk_url=f"ws://127.0.0.1:{server.sockets[0].getsockname()[1]}/asr",stop_timeout=.05,translation=TranslationConfig(enabled=True,provider="test"))
            raw=Browser();raw.incoming.put_nowait({"type":"websocket.receive","bytes":b""})
            r=OperationalRun();r.reset("a");adapter=OperatorBrowser(raw,"a",r)
            with patch("app.translation.engine.provider_from_config",return_value=(Blocked(),TranslationStatus("ready","blocked",""))):
                with self.assertRaisesRegex(TimeoutError,"finalization"):
                    await asyncio.wait_for(relay(adapter,settings,"a"),1)
            self.assertEqual(r.outcome,"incomplete");self.assertEqual(r.failure_reason,"stop_timeout")
            self.assertEqual(r.translator.metrics.cancelled,1);self.assertFalse(r.translator._workers)


if __name__=="__main__":unittest.main()

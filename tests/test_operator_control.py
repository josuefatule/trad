import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.server import serve

from app.main import Settings, create_app
from app.operator_control import OperatorAuthority, OperatorBrowser, OperatorConfig, operational_error
from app.translation import TranslationConfig
from tests.test_overlay import translated


def local_client(app, **kwargs):
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000), **kwargs)


def authorize(client):
    return client.get("/api/operator/bootstrap").json()["control_token"]


def headers(token):
    return {"origin": "http://localhost", "x-operator-token": token}


async def controlled_relay(browser, settings, session_id, caption_hub):
    await browser.send_json({"type":"status","state":"connecting"})
    caption_hub.set_state(session_id,"live")
    await browser.send_json({"type":"config","capabilities":{},"state":"connected"})
    while True:
        incoming = await browser.receive()
        if incoming["type"] == "websocket.disconnect":
            raise WebSocketDisconnect()
        if incoming.get("bytes") == b"":
            caption_hub.set_state(session_id,"stopped")
            await browser.send_json({"type":"status","state":"stopped"})
            return


class OperatorControlTests(unittest.TestCase):
    def setUp(self):
        self.app=create_app(Settings(log_dir="logs/tests",translation=TranslationConfig()))

    def test_bootstrap_no_secrets_and_no_false_service_readiness(self):
        with local_client(self.app) as client:
            response=client.get("/api/operator/bootstrap")
            self.assertEqual(response.headers["cache-control"],"no-store")
            data=response.json(); token=data["control_token"]
            self.assertEqual(data["protocol_version"],1)
            state=client.get("/api/operator/status",headers=headers(token)).json()
            self.assertEqual(state["state"],"waiting")
            self.assertFalse(state["translator_verified"])
            self.assertEqual(state["overlay_connections"],0)
            self.assertEqual(state["latency_diagnostics"]["backend_samples"],[])
            self.assertNotIn(token,json.dumps(client.get("/api/overlay/status").json()))
            self.assertNotIn("auth_key",json.dumps(state))

    def test_remote_host_origin_and_missing_authorization_rejected(self):
        with TestClient(self.app,base_url="http://localhost",client=("192.0.2.1",1)) as remote:
            self.assertEqual(remote.get("/api/operator/bootstrap").status_code,403)
        with local_client(self.app) as client:
            self.assertEqual(client.get("/api/operator/bootstrap",headers={"host":"evil.example"}).status_code,403)
            self.assertEqual(client.get("/api/operator/bootstrap",headers={"origin":"https://evil.example"}).status_code,403)
            self.assertEqual(client.get("/api/operator/status").status_code,403)
            token=authorize(client)
            for h in ({}, {"x-operator-token":token}, {**headers(token),"origin":"http://evil.example"},
                      {**headers(token),"host":"localhost.evil.example"}):
                self.assertEqual(client.post("/api/operator/clear",headers=h,json={}).status_code,403)
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("ws://localhost/ws/session",headers={"origin":"http://localhost"}):pass
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("ws://localhost/ws/session",subprotocols=["operator.v1",token],headers={"origin":"http://evil.example"}):pass

    def test_clear_without_session_is_safe_noop(self):
        with local_client(self.app) as client:
            token=authorize(client)
            response=client.post("/api/operator/clear",headers=headers(token),json={"protocol_version":1,"session_id":None,"visual_generation":0})
            self.assertEqual(response.status_code,200)
            self.assertFalse(response.json()["applied"])
            self.assertEqual(self.app.state.caption_hub.event_id,0)

    def test_live_clear_all_observers_reconnect_new_caption_and_no_order_reset(self):
        with patch("app.main.relay",controlled_relay),local_client(self.app) as client:
            owner=authorize(client); outsider=authorize(client)
            with client.websocket_connect("ws://localhost/ws/session",subprotocols=["operator.v1",owner],headers={"origin":"http://localhost"}) as operator:
                session=operator.receive_json()["session_id"];operator.receive_json()
                hub=self.app.state.caption_hub
                with client.websocket_connect("ws://localhost/ws/overlay") as first,client.websocket_connect("ws://localhost/ws/overlay") as second:
                    first.receive_json();second.receive_json()
                    client.portal.call(hub.publish,translated(1,session,text="Before clear."))
                    first.receive_json();second.receive_json()
                    body={"protocol_version":1,"session_id":session,"visual_generation":0}
                    self.assertEqual(client.post("/api/operator/clear",headers=headers(outsider),json=body).status_code,403)
                    with patch.object(hub,"publish",wraps=hub.publish) as publish:
                        result=client.post("/api/operator/clear",headers=headers(owner),json=body)
                        publish.assert_not_called()
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(hub.state,"live"); self.assertEqual(hub.sequence,1)
                    self.assertEqual(hub.snapshot()["captions"],[])
                    for overlay in (first,second):
                        clear=overlay.receive_json()
                        self.assertEqual(clear["type"],"captions_cleared")
                        self.assertEqual(clear["visual_generation"],1)
                        self.assertEqual(clear["cleared_through_sequence"],1)
                    # Public observer commands cannot clear again.
                    first.send_json({"type":"captions_cleared","session_id":session})
                    first.send_json({"type":"clock_probe","client_sent_ms":1})
                    self.assertEqual(first.receive_json()["type"],"clock_sync")
                    self.assertEqual(hub.visual_generation,1)
                    self.assertEqual(client.post("/api/operator/clear",headers=headers(owner),json=body).status_code,409)
                    with client.websocket_connect("ws://localhost/ws/overlay") as reconnected:
                        snapshot=reconnected.receive_json()
                        self.assertIsNone(snapshot["caption"])
                        self.assertEqual(snapshot["captions"],[])
                        self.assertEqual(snapshot["cleared_through_sequence"],1)
                        client.portal.call(hub.publish,translated(2,session,text="After clear."))
                        for overlay in (first,second,reconnected):
                            caption=overlay.receive_json()
                            self.assertEqual(caption["caption"]["sequence"],2)
                            self.assertEqual(caption["visual_generation"],1)
                    self.assertEqual(client.get("/api/operator/status",headers=headers(owner)).json()["overlay_connections"],2)
                operator.send_bytes(b"")
                self.assertEqual(operator.receive_json()["state"],"stopped")

    def test_invalid_protocol_and_generation_rejected(self):
        with local_client(self.app) as client:
            token=authorize(client)
            for body in ({"protocol_version":0,"session_id":None,"visual_generation":0},
                         {"protocol_version":1,"session_id":"old","visual_generation":0},
                         {"protocol_version":1,"session_id":None,"visual_generation":True}):
                self.assertEqual(client.post("/api/operator/clear",headers=headers(token),json=body).status_code,409)

    def test_safe_error_categories_and_validated_diagnostic_thresholds(self):
        for source,code in (("HTTP Error 403: PRIVATE","translation_auth"),("translation_timeout after 8s","translation_timeout"),
                            ("translation_queue_full","translation_queue_full"),(ConnectionError("PRIVATE"),"wlk_disconnected")):
            actual,message=operational_error(source)
            self.assertEqual(actual,code);self.assertNotIn("PRIVATE",message)
        for kwargs in ({"poll_seconds":.01},{"sustained_seconds":float("nan")},{"minimum_samples":1}):
            with self.assertRaises(ValueError):OperatorConfig(**kwargs)

    def test_visual_epoch_reset_and_stale_paint_telemetry_rejected(self):
        hub=self.app.state.caption_hub
        hub.begin("a")
        with self.assertRaises(ValueError):hub.clear_captions("a",0)
        hub.set_state("a","live");hub.publish(translated())
        observer=hub.subscribe()
        hub.record_client_sample(observer,{"session_id":"a","sequence":1,"visual_generation":0,"visible_line_count":2})
        self.assertEqual(observer.diagnostics["visible_line_count"],2)
        hub.clear_captions("a",0)
        self.assertEqual(observer.diagnostics,{})
        hub.record_client_sample(observer,{"session_id":"a","sequence":1,"visual_generation":0,"visible_line_count":2})
        self.assertEqual(observer.diagnostics,{})
        hub.set_state("a","draining")
        with self.assertRaises(ValueError):hub.clear_captions("a",1)
        hub.set_state("a","stopped");hub.begin("b")
        self.assertEqual((hub.sequence,hub.visual_generation,hub.cleared_through_sequence),(0,0,0))
        self.assertEqual(hub.snapshot()["captions"],[])


class OperatorPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_owner_is_rechecked_after_awaiting_control_body(self):
        authority=OperatorAuthority();old_owner=authority.issue();new_owner=authority.issue()
        with patch("app.main.OperatorAuthority",return_value=authority):
            app=create_app(Settings(log_dir="logs/tests",translation=TranslationConfig()))
        hub=app.state.caption_hub;hub.begin("old");hub.set_state("old","live");authority.owner=old_owner
        class Request:
            client=SimpleNamespace(host="127.0.0.1")
            url=SimpleNamespace(scheme="http")
            headers={"host":"localhost","origin":"http://localhost","x-operator-token":old_owner}
            async def json(self):
                # New owner takes over while the old request body is arriving.
                hub.set_state("old","stopped");hub.begin("new");hub.set_state("new","live")
                authority.owner=new_owner;hub.publish(translated(1,"new"))
                return {"protocol_version":1,"session_id":"new","visual_generation":0}
        endpoint=next(route.endpoint for route in app.routes if getattr(route,"path",None)=="/api/operator/clear")
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as rejected:
            await endpoint(Request())
        self.assertEqual(rejected.exception.status_code,403)
        self.assertEqual(hub.visual_generation,0)
        self.assertIsNotNone(hub.snapshot()["caption"])

    async def test_provider_failures_are_sanitized_without_altering_translation_fields(self):
        class Socket:
            async def send_json(self,data):self.data=data
        socket=Socket();browser=OperatorBrowser(socket,"current")
        for error,code in (("HTTP Error 403: PRIVATE_KEY","translation_auth"),
                           ("translation_timeout PRIVATE_KEY","translation_timeout"),
                           ("translation_queue_full PRIVATE_KEY","translation_queue_full")):
            result={"sequence":3,"segment_id":"current:3","raw_text":"RAW","normalized_text":"NORMALIZED",
                    "success":False,"error":error}
            await browser.send_json({"type":"translation","translation":result})
            self.assertEqual(socket.data["translation"]["error_code"],code)
            self.assertNotIn("PRIVATE_KEY",json.dumps(socket.data))
            self.assertEqual(socket.data["translation"]["raw_text"],"RAW")
            self.assertEqual(socket.data["translation"]["sequence"],3)
            self.assertEqual(result["error"],error)  # Original result not mutated.

    async def test_clear_during_real_relay_keeps_final_flush_and_histories(self):
        async def wlk(ws):
            await ws.send(json.dumps({"type":"config","useAudioWorklet":True,"mode":"full"}))
            self.assertEqual(await ws.recv(),b"\x00\x00")
            await ws.send(json.dumps({"lines":[{"speaker":1,"text":"Presión systólica."}]}))
            self.assertEqual(await ws.recv(),b"")
            await ws.send(json.dumps({"lines":[{"speaker":1,"text":"Presión systólica. Función renal."}]}))
            await ws.send(json.dumps({"type":"ready_to_stop"}))
            await ws.wait_closed()
        async with serve(wlk,"127.0.0.1",0) as server:
            port=server.sockets[0].getsockname()[1]
            app=create_app(Settings(log_dir="logs/tests",wlk_url=f"ws://127.0.0.1:{port}/asr",
                                    translation=TranslationConfig(enabled=True,provider="mock")))
            def browser():
                with local_client(app) as client:
                    token=authorize(client)
                    with client.websocket_connect("ws://localhost/ws/session",subprotocols=["operator.v1",token],headers={"origin":"http://localhost"}) as ws:
                        session=ws.receive_json()["session_id"]
                        config=ws.receive_json();self.assertEqual(config["capabilities"]["captions_clear"],1)
                        ws.send_bytes(b"\x00\x00")
                        first=ws.receive_json();self.assertEqual(first["transcript"]["confirmed_text"],"Presión systólica.")
                        cleared=client.post("/api/operator/clear",headers=headers(token),json={"protocol_version":1,"session_id":session,"visual_generation":0})
                        self.assertEqual(cleared.status_code,200)
                        ws.send_bytes(b"")
                        raw=[];normalized=[];english=[]
                        while True:
                            message=ws.receive_json()
                            raw += [s["text"] for s in message.get("segmentation",{}).get("ready_segments",[])]
                            normalized += [s["normalized_text"] for s in message.get("normalization",{}).get("segments",[])]
                            if message["type"]=="translation":english.append(message["translation"])
                            if message.get("state")=="stopped":break
                        self.assertEqual(" ".join(raw),"Presión systólica. Función renal.")
                        self.assertEqual(" ".join(normalized),"Presión sistólica. Función renal.")
                        self.assertEqual([item["sequence"] for item in english],list(range(1,len(english)+1)))
                        self.assertTrue(all(item["success"] for item in english))
            await asyncio.wait_for(asyncio.to_thread(browser),10)

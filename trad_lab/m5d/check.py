"""Real frozen TRAD -> gateway ASGI -> viewer, entirely in memory, no TCP."""
import argparse
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch


async def check(plan, out):
    from trad_lab.m5d.prepare import verify
    data = verify(plan)
    copy = Path(data["copy"]).resolve()
    if Path(__file__).resolve().parents[2] != copy:
        raise ValueError("Run the test from the frozen copy")
    from trad_lab.m5b.memory import MemoryHTTP, MemorySocket, MemoryClosed
    from trad_lab.m5d.gateway import Policy, create_gateway, FILES, private_ipv4
    # A second defense: any TCP bind/listen or real provider call fails the test.
    import socket
    from app.translation.providers import DeepLTranslatorProvider
    import os
    os.environ["CAPTIONS_LOG_DIR"] = str(out / "operational_logs")
    from app.main import app as trad
    hub = trad.state.caption_hub
    authority = trad.state.operator_authority
    policy = Policy("192.168.50.10", "192.168.50.20", copy)  # Synthetic fixture, never assigned/bound.
    checks, wire = [], []

    def ok(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    class Source:
        connections = 0
        closed = 0
        originals = []
        async def config(self):
            async with MemoryHTTP(trad) as http:
                return (await http.get("/api/overlay/config")).json()

        @asynccontextmanager
        async def subscribe(self):
            inner = await MemorySocket(trad, "/ws/overlay", port=18010).open()
            self.connections += 1
            class ReadOnly:
                async def recv(self):
                    raw = await inner.recv()
                    source.originals.append(raw)
                    return raw
                # Deliberately no send method: viewer input cannot reach TRAD.
            try:
                yield ReadOnly()
            finally:
                await inner.close()
                self.closed += 1
    source = Source()
    gateway = create_gateway(policy, source)
    class Remote:
        def __init__(self, app, client=policy.viewer_ip):
            self.app, self.client = app, client
        async def __call__(self, scope, receive, send):
            scope = {**scope, "client": (self.client, 50001)}
            await self.app(scope, receive, send)

    def viewer(path="/ws/overlay", client=policy.viewer_ip, host=policy.host, origin=policy.origin, query=b""):
        headers = [(b"host", host.encode())]
        if origin is not None:
            headers.append((b"origin", origin.encode()))
        return MemorySocket(gateway, path, headers=headers, query=query, client=client, port=3000)

    async def send(ws, data):
        await ws.incoming.put({"type": "websocket.receive", "text": json.dumps(data)})

    async def receive(ws, kind):
        raw = await asyncio.wait_for(ws.recv(), 3)
        message = json.loads(raw)
        ok("event " + kind, message["type"] == kind)
        if kind != "clock_sync":
            ok("unaltered upstream JSON", raw in source.originals)
        wire.append(message)
        return message

    async with gateway.router.lifespan_context(gateway):
        async with MemoryHTTP(Remote(gateway), policy.origin) as remote:
            page = await remote.get("/overlay", headers={"cookie": "operator=private-not-forwarded"})
            ok("real overlay HTML exact", page.status_code == 200 and page.content == (copy / FILES["/overlay"]).read_bytes())
            ok("no cookie response", b"set-cookie" not in page.headers and b"private-not-forwarded" not in page.content)
            ok("no cache", page.headers[b"cache-control"] == b"no-store")
            for path, name in FILES.items():
                result = await remote.get(path)
                ok("exact asset " + path, result.status_code == 200 and result.content == (copy / name).read_bytes())
            config = await remote.get("/api/overlay/config")
            cfg = config.json()
            ok("original config 1920x1080 transparent timed queue", config.status_code == 200 and
               (cfg["canvas_width"], cfg["canvas_height"], cfg["background_opacity"], cfg["mode"]) == (1920,1080,0,"timed_queue"))
            ok("human replay display window only", cfg["min_display_ms"] == 10000 and cfg["max_display_ms"] == 30000)
            denied = ("/", "/operator", "/capture", "/m5c/physical-capture", "/api/operator/bootstrap",
                      "/api/operator/status", "/api/operator/clear", "/api/m5c/presentation", "/api/m5d/replay/start",
                      "/ws/session", "/health", "/api/overlay/status", "/overlay/preview", "/docs", "/openapi.json",
                      "/.env", "/.runtime/operator.json", "/logs/translation_trace.jsonl", "/corpus/cardio_01.wav",
                      "/app/main.py", "/static/operator.js", "/static/m5d_replay.js", "/static/../main.py",
                      "/static/%2e%2e/main.py", "/static/overlay.js/", "/overlay/", "/overlay?token=secret",
                      "/api/overlay/config?font_size=96", "/overlay?redirect=http://example.invalid")
            for path in denied:
                ok("denied GET " + path, (await remote.get(path)).status_code == 404)
            for method in ("HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE", "CONNECT"):
                ok("denied method " + method, (await remote.request(method, "/overlay")).status_code == 404)
            for bad in ({"origin": "https://evil.invalid"}, {"sec-fetch-site": "cross-site"}, {"host": "evil.invalid"}):
                ok("denied HTTP host/origin", (await remote.get("/overlay", headers=bad)).status_code == 404)
        async with MemoryHTTP(Remote(gateway, "192.168.50.99"), policy.origin) as remote:
            ok("denied other laptop", (await remote.get("/overlay")).status_code == 404)
        # Sanitization fails closed if the upstream contract unexpectedly includes secrets.
        with patch.object(source, "config", return_value={**cfg,"control_token":"private"}):
            async with MemoryHTTP(Remote(gateway), policy.origin) as remote:
                bad = await remote.get("/api/overlay/config")
                ok("upstream extra fields never serialized", bad.status_code == 503 and b"private" not in bad.content)

        for kwargs in ({"path":"/ws/session"}, {"path":"/api/operator/clear"}, {"client":"192.168.50.99"},
                       {"host":"evil.invalid"}, {"origin":"https://evil.invalid"}, {"origin":None}, {"query":b"token=x"}):
            bad = viewer(**kwargs)
            try:
                await asyncio.wait_for(bad.open(), 2)
                raise AssertionError("Forbidden websocket accepted")
            except MemoryClosed:
                checks.append("denied WebSocket " + str(kwargs))
            finally:
                await bad.close()

        async with MemoryHTTP(trad) as local:
            origin = "http://127.0.0.1:18010"
            boot = (await local.get("/api/operator/bootstrap", headers={"origin":origin})).json()
            token = boot["control_token"]
            def authorized():
                return {"x-operator-token":token,"origin":origin}
            async def command(action):
                response = await local.post("/api/m5d/replay/" + action, headers=authorized())
                ok("authorized replay " + action, response.status_code == 200)
                return response.json()
            async def presentation(hidden):
                response = await local.post("/api/m5c/presentation", headers=authorized(),
                    json={"session_id":hub.session_id,"visual_generation":hub.visual_generation,"hidden":hidden})
                ok("original presentation control", response.status_code == 200)

            ok("microphone capture page blocked in replay", (await local.get("/m5c/physical-capture")).status_code == 403)
            ok("unauthorized replay rejected", (await local.post("/api/m5d/replay/start")).status_code == 403)
            first = await command("start")
            ws = await viewer().open()
            snapshot = await receive(ws, "snapshot")
            ok("correct initial session", snapshot["session_id"] == first["session_id"])
            await command("next")
            caption = await receive(ws, "caption")
            ok("Spanish text and sequence unchanged", caption["caption"]["text"] == "[PRUEBA LAN] Subtítulos en español: conexión estable." and
               caption["caption"]["sequence"] == 1 and caption["caption"]["target_language"] == "es")
            before = (hub.session_id,hub.state,hub.sequence,hub.visual_generation,authority.owner)
            await send(ws,{"type":"clock_probe","client_sent_ms":100})
            sync = await receive(ws,"clock_sync")
            ok("clock host monotonic", sync["server_received_mono_ms"] <= sync["server_sent_mono_ms"])
            await send(ws,{"type":"render_sample","session_id":hub.session_id,"sequence":1,"visual_generation":0,
                           "hub_delivery_estimate_ms":1.5,"delivery_uncertainty_ms":2,"paint_delay_ms":.5})
            await send(ws,{"type":"stop","session_id":hub.session_id})
            try:
                await ws.recv()
                raise AssertionError("Command client was not closed")
            except MemoryClosed:
                pass
            await ws.close()
            ok("remote command cannot mutate TRAD", before == (hub.session_id,hub.state,hub.sequence,hub.visual_generation,authority.owner))
            ok("bounded local telemetry only", len(gateway.state.samples) == 1 and not hub.client_samples)

            ws = await viewer().open()
            snap = await receive(ws,"snapshot")
            ok("reconnect only current snapshot, no event replay", snap["caption"]["sequence"] == 1 and not snap["captions"])
            response = await local.post("/api/operator/clear", headers=authorized(), json={"protocol_version":1,
                "session_id":hub.session_id,"visual_generation":hub.visual_generation})
            ok("original CLEAR authorized", response.status_code == 200)
            await receive(ws,"captions_cleared")
            await command("next"); await receive(ws,"caption")
            await presentation(True); await receive(ws,"captions_cleared")
            await command("next")
            hidden = await receive(ws,"translator")
            ok("hide suppresses captions", hidden["state"] == "operator_hidden" and hub.last_caption is None)
            await ws.close()
            ws = await viewer().open()
            hidden = await receive(ws,"snapshot")
            ok("reconnect during hide empty", hidden["caption"] is None and hidden["captions"] == [])
            await presentation(False); await receive(ws,"captions_cleared")
            await command("next")
            resumed = await receive(ws,"caption")
            ok("resume only new content", resumed["caption"]["sequence"] == 4 and "REANUDAR" in resumed["caption"]["text"])
            # Actual recovered owner invalidates the old token, including replay controls.
            previous = token
            token = authority.resume(token, authority.resume_secrets[token])
            ok("old owner token rejected", (await local.post("/api/m5d/replay/next", headers={"origin":origin,"x-operator-token":previous})).status_code == 403)
            # No viewer can publish/control, submit binary, malformed or oversized
            # payloads, even after a valid handshake from the permitted laptop.
            before = (hub.session_id, hub.state, hub.sequence, hub.visual_generation, authority.owner)
            for payload in ({"type":"start"}, {"type":"clear"}, {"type":"hide"}, {"type":"resume"},
                            {"type":"caption","text":"injected"}, {"type":"clock_probe","client_sent_ms":-1},
                            {"type":"clock_probe","client_sent_ms":0,"command":"clear"}, [], None):
                malicious = await viewer().open(); await receive(malicious,"snapshot")
                await send(malicious,payload)
                try:
                    await malicious.recv(); raise AssertionError("Malicious client was not closed")
                except MemoryClosed:
                    checks.append("rejected viewer message " + str(payload))
                await malicious.close()
            for payload in ({"type":"websocket.receive","bytes":b"clear"},
                            {"type":"websocket.receive","text":"x"*8193},
                            {"type":"websocket.receive","text":"{invalid"}):
                malicious = await viewer().open(); await receive(malicious,"snapshot")
                await malicious.incoming.put(payload)
                try:
                    await malicious.recv(); raise AssertionError("Invalid frame was not closed")
                except MemoryClosed:
                    checks.append("rejected invalid frame")
                await malicious.close()
            ok("all hostile messages preserve publisher state", before == (hub.session_id,hub.state,hub.sequence,hub.visual_generation,authority.owner))
            await command("stop"); await receive(ws,"captions_cleared"); await receive(ws,"session")
            await command("start"); fresh = await receive(ws,"session"); await receive(ws,"session")
            await command("next"); fresh_caption = await receive(ws,"caption")
            ok("new session starts at one without contamination", fresh["session_id"] != first["session_id"] and
               fresh_caption["caption"]["sequence"] == 1 and hub.cleared_through_sequence == 0)
            # Gateway lifespan shutdown while replay stays live and owned.
            running = (hub.session_id,hub.state,hub.sequence,authority.owner)
            self_state = running
            for index in range(3):
                extra = await viewer().open(); await receive(extra,"snapshot")
                # Keep four simultaneous connections until the limit check.
                if index == 0: extras = []
                extras.append(extra)
            denied = viewer()
            try:
                await denied.open(); raise AssertionError("Viewer budget bypassed")
            except MemoryClosed:
                checks.append("four viewer connection budget")
            finally:
                await denied.close()
            for extra in extras:
                await extra.close()
            # Deliberately leave ws active; the enclosing gateway lifespan closes it.

    await ws.close()
    ok("closing gateway preserves backend session", self_state == (hub.session_id,hub.state,hub.sequence,authority.owner))
    ok("all upstream subscriptions released", not hub.subscribers and source.connections == source.closed and not gateway.state.active)
    for invalid in ("0.0.0.0","127.0.0.1","8.8.8.8","169.254.1.1","::1"):
        try:
            private_ipv4(invalid); raise AssertionError("Unsafe bind accepted")
        except ValueError:
            checks.append("unsafe bind rejected " + invalid)
    (out / "wire.json").write_text(json.dumps(wire,ensure_ascii=False,indent=2),encoding="utf-8")
    result = {"status":"PASS","checks":len(checks),"names":checks,"upstream_opened":source.connections,
              "upstream_closed":source.closed,"scope":"Real frozen TRAD and gateway ASGI, no TCP, microphone, ASR inference or provider"}
    (out / "result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k != "names"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan",required=True)
    parser.add_argument("--out",required=True)
    args = parser.parse_args()
    out = Path(args.out).resolve(); out.mkdir(parents=True,exist_ok=False)
    # Do not patch asyncio's own Windows socketpair; forbid network operations once
    # its event loop exists. All application transports above are injected ASGI.
    async def guarded():
        import socket
        from app.translation.providers import DeepLTranslatorProvider
        with patch.object(socket.socket,"bind",side_effect=AssertionError("TCP bind forbidden")), \
             patch.object(socket.socket,"listen",side_effect=AssertionError("TCP listen forbidden")), \
             patch.object(DeepLTranslatorProvider,"translate",side_effect=AssertionError("Real DeepL forbidden")):
            await asyncio.wait_for(check(args.plan,out),45)
    asyncio.run(guarded())

"""Explicit HTTP allowlist and receive-only upstream WebSocket. Current application assets; no control or translation endpoints.

The peer IP is a view-only network capability, independent of Operator. Client
messages NEVER reach TRAD: clock replies and bounded diagnostics stay here.
"""
import asyncio
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
import http.client
import ipaddress
import json
import math
from pathlib import Path
import time

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed


STATIC = ("overlay.css", "overlay_geometry.js", "caption_renderer.js",
          "overlay_latency.js", "overlay.js")
FILES = {"/overlay": "app/templates/overlay.html",
         **{"/static/" + name: "app/static/" + name for name in STATIC}}
GET_PATHS = frozenset((*FILES, "/api/overlay/config"))
PRIVATE = tuple(ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def private_ipv4(value):
    address = ipaddress.IPv4Address(value)
    if not any(address in network for network in PRIVATE):
        raise ValueError("An explicit RFC1918 IPv4 address is required")
    return str(address)


@dataclass(frozen=True)
class Policy:
    lan_ip: str
    viewer_ip: str
    copy: Path

    def __post_init__(self):
        private_ipv4(self.lan_ip)
        private_ipv4(self.viewer_ip)
        if self.lan_ip == self.viewer_ip:
            raise ValueError("Select the second laptop, not this computer")

    @property
    def host(self):
        return self.lan_ip + ":3000"

    @property
    def origin(self):
        return "http://" + self.host


class LoopbackUpstream:
    """Fixed targets, no ambient proxy, redirects, cookies or client headers."""
    def __init__(self, port=8010):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid loopback port')
        self.port = port

    async def config(self):
        def get():
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
            try:
                connection.request("GET", "/api/overlay/config", headers={"Accept": "application/json"})
                response = connection.getresponse()
                body = response.read(32769)
                if response.status != 200 or len(body) > 32768:
                    raise ValueError("Upstream configuration unavailable")
                return json.loads(body)
            finally:
                connection.close()
        return await asyncio.to_thread(get)

    @asynccontextmanager
    async def subscribe(self):
        async with connect(f"ws://127.0.0.1:{self.port}/ws/overlay", proxy=None,
                           open_timeout=3, close_timeout=2, max_size=1048576,
                           max_queue=4, compression=None) as connection:
            yield connection


def headers(policy):
    return {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; connect-src 'self' ws://" + policy.host + "; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            "Permissions-Policy": "microphone=(), camera=(), geolocation=()"}


def permitted(scope, policy, websocket=False):
    # Ignore X-Forwarded-*; the server also disables proxy-header trust.
    if not scope.get("client") or scope["client"][0] != policy.viewer_ip:
        return False
    raw = scope.get("headers", [])
    def values(name):
        return [v.decode("latin1") for k, v in raw if k.lower() == name]
    if values(b"host") != [policy.host] or scope.get("query_string"):
        return False
    origin = values(b"origin")
    if origin and origin != [policy.origin]:
        return False
    if websocket and origin != [policy.origin]:
        return False
    if any(v not in ("same-origin", "none") for v in values(b"sec-fetch-site")):
        return False
    return True


def create_gateway(policy, upstream=None):
    upstream = upstream or LoopbackUpstream()
    active = set()
    diagnostics = deque(maxlen=128)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            # Closing this process only cancels view subscriptions, never sessions.
            tasks = tuple(active)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.active = active
    app.state.samples = diagnostics
    app.state.upstream = upstream

    # This guard runs before routing, including automatic HEAD, redirects and docs.
    class Guard:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            kind = scope["type"]
            if kind in ("http", "websocket"):
                allowed = permitted(scope, policy, kind == "websocket")
                path = scope["path"]
                if kind == "http":
                    allowed = allowed and scope["method"] == "GET" and path in GET_PATHS
                    if not allowed:
                        await Response(status_code=404, headers=headers(policy))(scope, receive, send)
                        return
                elif not allowed or path != "/ws/overlay":
                    await send({"type": "websocket.close", "code": 1008})
                    return
            await self.app(scope, receive, send)
    app.add_middleware(Guard)

    for route, relative in FILES.items():
        def handler_for(relative):
            async def serve():
                return FileResponse(Path(policy.copy) / relative, headers=headers(policy))
            return serve
        app.add_api_route(route, handler_for(relative), methods=["GET"])

    @app.get("/api/overlay/config")
    async def config():
        try:
            data = await upstream.config()
            # Allow only the public renderer contract; never serialize upstream extras.
            from app.overlay.config import CaptionConfig
            from dataclasses import fields
            allowed = {field.name for field in fields(CaptionConfig)}
            if not isinstance(data, dict) or set(data) != allowed:
                raise ValueError("Unexpected configuration schema")
            validated = CaptionConfig(**data)
            if (validated.canvas_width, validated.canvas_height) != (1920, 1080):
                raise ValueError("Unexpected canvas")
            return JSONResponse(validated.to_dict(), headers=headers(policy))
        except (OSError, ValueError, TypeError, TimeoutError, http.client.HTTPException):
            return Response(status_code=503, headers=headers(policy))

    @app.websocket("/ws/overlay")
    async def overlay(browser: WebSocket):
        if len(active) >= 4:
            await browser.close(code=1013)
            return
        task = asyncio.current_task()
        active.add(task)
        tasks = []
        send_lock = asyncio.Lock()
        current = {"session_id": None, "sequence": 0, "visual_generation": 0}

        async def send_text(raw):
            async with send_lock:
                await asyncio.wait_for(browser.send_text(raw), 2)

        try:
            async with upstream.subscribe() as source:
                await browser.accept(headers=[(k.lower().encode(), v.encode()) for k, v in headers(policy).items()])

                async def events():
                    while True:
                        raw = await source.recv()
                        if not isinstance(raw, str) or len(raw.encode()) > 1048576:
                            raise ValueError("Invalid upstream frame")
                        message = json.loads(raw)
                        if message.get("protocol_version") != 3 or message.get("type") not in {
                                "snapshot", "session", "caption", "captions_cleared", "translator"}:
                            raise ValueError("Unexpected upstream protocol")
                        direction = message.get("direction")
                        if direction and direction.get("target_language") not in {"en", "es"}:
                            raise ValueError("Unsupported overlay direction")
                        current.update(session_id=message.get("session_id"),
                                       visual_generation=message.get("visual_generation", 0),
                                       sequence=message.get("sequence", (message.get("caption") or {}).get("sequence", current["sequence"])))
                        await send_text(raw)  # Byte-identical caption/event JSON, no replay cache.

                async def client_messages():
                    window, count = time.monotonic(), 0
                    while True:
                        frame = await browser.receive()
                        if frame["type"] == "websocket.disconnect":
                            return
                        raw = frame.get("text")
                        if raw is None or len(raw.encode()) > 8192:
                            raise ValueError("Client frame budget")
                        now = time.monotonic()
                        if now - window >= 1:
                            window, count = now, 0
                        count += 1
                        if count > 60:
                            raise ValueError("Client rate budget")
                        data = json.loads(raw)
                        if not isinstance(data, dict):
                            raise ValueError("Client schema")
                        kind = data.get("type")
                        if kind == "clock_probe":
                            sent = data.get("client_sent_ms")
                            if set(data) != {"type", "client_sent_ms"} or type(sent) not in (int, float) or not math.isfinite(sent) or not 0 <= sent <= 1e12:
                                raise ValueError("Clock schema")
                            await send_text(json.dumps({"type": "clock_sync", "protocol_version": 3,
                                "client_sent_ms": sent, "server_received_mono_ms": now * 1000,
                                "server_sent_mono_ms": time.monotonic() * 1000,
                                "server_clock_resolution_ms": time.get_clock_info("monotonic").resolution * 1000}))
                        elif kind in {"render_sample", "connection_health", "display_drop"}:
                            # Keep only numeric observations, on this process, never in TRAD.
                            if data.get("session_id") != current["session_id"]:
                                continue
                            if data.get("visual_generation", current["visual_generation"]) != current["visual_generation"]:
                                continue
                            numeric = {k: v for k, v in data.items() if k in {
                                "sequence", "renderer_delay_ms", "paint_delay_ms", "hub_delivery_estimate_ms",
                                "delivery_uncertainty_ms", "browser_received_ms", "browser_rendered_ms",
                                "visual_queue_depth", "visible_caption_count", "visible_line_count", "attempts", "downtime_ms"}
                                and type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1e12}
                            diagnostics.append({"type": kind, **current, **numeric,
                                                "gateway_received_mono_ms": now * 1000})
                        else:
                            raise ValueError("Read-only viewer")

                tasks = [asyncio.create_task(events()), asyncio.create_task(client_messages())]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for finished in done:
                    finished.result()
        except (WebSocketDisconnect, ConnectionClosed, ConnectionError, OSError, TimeoutError, ValueError, TypeError):
            pass  # No payloads, tokens, cookies, query strings or exceptions in logs.
        finally:
            for child in tasks:
                child.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            active.discard(task)
            try:
                await browser.close(code=1001)
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass

    return app

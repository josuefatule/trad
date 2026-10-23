import logging
import asyncio
import math
import time
import os
import secrets
import json
import subprocess
import getpass
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field, replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.environment import load_project_env

load_project_env()

from app.asr.whisperlivekit_client import relay
from app.captions.segment_manager import SegmentConfig
from app.captions.terminology_normalizer import NormalizerConfig
from app.translation import TranslationConfig
from app.overlay.config import CaptionConfig
from app.overlay.hub import CaptionHub
from app.operator_control import OperatorAuthority, OperatorBrowser, OperatorConfig, local_request, operational_error
from app.translation.engine import provider_from_config
from app.reliability import OperationalRun, ReliabilityConfig, SafeLogFilter, incident
from app.session_direction import DEFAULT_DIRECTION, direction_from_id

ROOT = Path(__file__).resolve().parent


@dataclass
class Settings:
    wlk_url: str = os.getenv("WLK_WS_URL", "ws://localhost:8000/asr")
    language: str = os.getenv("CAPTIONS_LANGUAGE", "es")
    direction: dict | None = None
    require_language_ack: bool = False
    log_raw: bool = os.getenv("CAPTIONS_LOG_RAW", "0") == "1"
    log_dir: str = os.getenv("CAPTIONS_LOG_DIR", str(ROOT.parent / "logs"))
    connect_timeout: float = float(os.getenv("CAPTIONS_CONNECT_TIMEOUT", "15"))
    stop_timeout: float = float(os.getenv("CAPTIONS_STOP_TIMEOUT", "120"))
    segments: SegmentConfig = field(default_factory=SegmentConfig.from_env)
    normalizer: NormalizerConfig = field(default_factory=NormalizerConfig.from_env)
    translation: TranslationConfig = field(default_factory=TranslationConfig.from_env)
    captions: CaptionConfig = field(default_factory=CaptionConfig.from_env)
    operator: OperatorConfig = field(default_factory=OperatorConfig.from_env)
    reliability: ReliabilityConfig = field(default_factory=ReliabilityConfig.from_env)

    def __post_init__(self):
        if not math.isfinite(self.connect_timeout) or not 0<self.connect_timeout<=60:
            raise ValueError("CAPTIONS_CONNECT_TIMEOUT must be within (0,60]")
        if not math.isfinite(self.stop_timeout) or not 0<self.stop_timeout<=300:
            raise ValueError("CAPTIONS_STOP_TIMEOUT must be within (0,300]")


def create_app(settings=None):
    settings = settings or Settings()
    logger = logging.getLogger("captions")
    authority = OperatorAuthority()
    run = OperationalRun(settings.reliability)
    session_open = False
    closure_acknowledged = True

    def inactive_safe():
        return (not session_open and hub.state not in {"connecting", "live", "draining"}
                and (run.outcome != "incomplete" or closure_acknowledged))
    admin_code = secrets.token_urlsafe(32)
    admin_path = ROOT.parent / ".runtime" / f"operator-{os.getpid()}.json"

    def save_admin_code():
        admin_path.parent.mkdir(parents=True,exist_ok=True)
        admin_path.write_text(json.dumps({"code":admin_code}),encoding="utf-8")
        admin_path.chmod(0o600)
        if os.name=="nt":
            account=os.environ.get("USERDOMAIN","")+"\\"+getpass.getuser()
            result=subprocess.run(["icacls",str(admin_path),"/inheritance:r","/grant:r",account+":(F)","*S-1-5-18:(F)"],capture_output=True)
            if result.returncode:raise RuntimeError("Cannot restrict local administrative recovery file ACL")

    @asynccontextmanager
    async def lifespan(app):
        folder = Path(settings.log_dir)
        folder.mkdir(parents=True, exist_ok=True)
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        handlers = [logging.StreamHandler(), RotatingFileHandler(
            folder / "development.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
        logger.setLevel(logging.INFO)
        logger.propagate = False
        for handler in handlers:
            handler.setFormatter(formatter)
            handler.addFilter(SafeLogFilter(lambda:(settings.translation.deepl_auth_key,admin_code,
                *authority.tokens,*authority.resume_secrets.values()),allow_text=settings.log_raw))
            logger.addHandler(handler)
        save_admin_code()
        raw = logging.getLogger("captions.raw")
        raw.propagate = False
        raw_handler = None
        if settings.log_raw:
            raw_handler = RotatingFileHandler(folder / "wlk-raw.log", maxBytes=10_000_000,
                                              backupCount=3, encoding="utf-8")
            raw_handler.setFormatter(formatter)
            raw_handler.addFilter(SafeLogFilter(lambda:(settings.translation.deepl_auth_key,admin_code,
                *authority.tokens,*authority.resume_secrets.values()),allow_text=True))
            raw.addHandler(raw_handler)
        yield
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        if raw_handler:
            raw.removeHandler(raw_handler)
            raw_handler.close()
        if admin_path.exists() and json.loads(admin_path.read_text(encoding="utf-8")).get("code")==admin_code:
            admin_path.unlink()

    app = FastAPI(lifespan=lifespan)
    hub = CaptionHub(settings.captions)
    app.state.caption_hub = hub
    app.state.operational_run=run
    app.state.operator_authority=authority
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

    @app.get("/health")
    async def health():
        # App liveness only. WLK readiness is verified during each handshake.
        return {"status": "ok", "language": settings.language, "wlk_check": "on_session_connect"}

    @app.get("/")
    async def index():
        return RedirectResponse("/operator")

    @app.get("/operator")
    async def operator():
        return FileResponse(ROOT / "templates" / "operator.html")

    @app.get("/capture")
    async def capture():
        return FileResponse(ROOT / "templates" / "operator.html")

    @app.get("/api/operator/bootstrap")
    async def operator_bootstrap(request: Request):
        if not local_request(request):
            raise HTTPException(403, "Local same-origin operator required")
        try:
            token = authority.issue()
        except ValueError:
            raise HTTPException(429, "Too many operator tabs")
        return JSONResponse({"protocol_version": 1, "capabilities": {"operator_console": 1, "captions_clear": 1,"operator_recovery":1,"session_direction":1},
                             "default_direction": DEFAULT_DIRECTION,
                             "control_token": token,"resume_secret":authority.resume_secrets[token],
                             "server_pid":os.getpid(), "diagnostics_config": asdict(settings.operator)},
                            headers={"Cache-Control": "no-store"})

    @app.post("/api/operator/resume")
    async def operator_resume(request: Request):
        if not local_request(request,require_origin=True):raise HTTPException(403,"Local origin required")
        data=await request.json()
        try:token=authority.resume(request.headers.get("x-operator-token"),data.get("resume_secret"))
        except (ValueError,AttributeError):raise HTTPException(403,"Recovery authorization rejected")
        return JSONResponse({"protocol_version":1,"capabilities":{"operator_console":1,"captions_clear":1,"operator_recovery":1,"session_direction":1},
            "default_direction": DEFAULT_DIRECTION,
            "control_token":token,"resume_secret":authority.resume_secrets[token],"server_pid":os.getpid(),
            "diagnostics_config":asdict(settings.operator)},headers={"Cache-Control":"no-store"})

    @app.post("/api/operator/recover")
    async def operator_recover(request: Request):
        nonlocal admin_code
        token=request.headers.get("x-operator-token")
        if not local_request(request,require_origin=True) or not authority.valid(token):raise HTTPException(403,"Local authorization required")
        data=await request.json()
        if not authority.valid(token):raise HTTPException(403,"Authorization expired")
        if (not isinstance(data,dict) or not secrets.compare_digest(str(data.get("admin_code","")).encode(),admin_code.encode())):
            raise HTTPException(403,"Administrative authorization rejected")
        now=time.monotonic()
        if data.get("session_id")!=hub.session_id or (authority.owner_seen is not None and now-authority.owner_seen<=settings.reliability.owner_timeout_seconds):
            raise HTTPException(409,"Owner is still available or session changed")
        previous=authority.owner
        if previous:authority.tokens.pop(previous,None);authority.resume_secrets.pop(previous,None)
        authority.owner=token;authority.owner_seen=now;authority.recoveries+=1
        admin_code=secrets.token_urlsafe(32);save_admin_code()
        incident("operator","administrative_recovery",hub.session_id,outcome="success")
        return {"protocol_version":1,"recovered":True,"session_id":hub.session_id}

    @app.post("/api/operator/stop")
    async def operator_stop(request: Request):
        token=request.headers.get("x-operator-token")
        if not local_request(request,require_origin=True) or not authority.valid(token) or authority.owner!=token:
            raise HTTPException(403,"Current session owner required")
        data=await request.json()
        if not authority.valid(token) or authority.owner!=token or data.get("session_id")!=hub.session_id:
            raise HTTPException(409,"Session changed")
        if hub.state not in {"connecting","live","draining"}:return {"protocol_version":1,"requested":False}
        requested=await run.request_stop()
        return {"protocol_version":1,"requested":requested}

    @app.post("/api/operator/translator-reset")
    async def translator_reset(request: Request):
        token=request.headers.get("x-operator-token")
        if not local_request(request,require_origin=True) or not authority.valid(token) or authority.owner!=token:
            raise HTTPException(403,"Current session owner required")
        data=await request.json()
        if not authority.valid(token) or authority.owner!=token or not isinstance(data,dict) or data.get("session_id")!=hub.session_id:
            raise HTTPException(409,"Session changed")
        rearmed=bool(run.translator and run.translator.rearm())
        return {"protocol_version":1,"rearmed":rearmed}

    @app.post("/api/operator/acknowledge-stop")
    async def acknowledge_stop(request: Request):
        nonlocal closure_acknowledged
        token = request.headers.get("x-operator-token")
        if not local_request(request, require_origin=True) or not authority.valid(token) or authority.owner != token:
            raise HTTPException(403, "Current session owner required")
        data = await request.json()
        if not authority.valid(token) or authority.owner != token:
            raise HTTPException(403, "Current session owner required")
        if (session_open or hub.state in {"connecting", "live", "draining"} or
                not isinstance(data, dict) or data.get("session_id") != hub.session_id or run.outcome != "incomplete"):
            raise HTTPException(409, "Session must be fully closed with an incomplete outcome")
        closure_acknowledged = True
        # Acknowledge loss, never rewrite the outcome or replay failed text.
        return {"protocol_version": 1, "acknowledged": True, "session_id": hub.session_id}

    @app.get("/api/operator/status")
    async def operator_status(request: Request):
        token = request.headers.get("x-operator-token")
        if not local_request(request) or not authority.valid(token):
            raise HTTPException(403, "Local operator authorization required")
        if authority.owner==token and request.headers.get("x-operator-role")!="capture":authority.owner_seen=time.monotonic()
        _, configured = provider_from_config(settings.translation)
        translator = (hub.translation_status_getter()["status"] if hub.translation_status_getter
                      else configured.to_dict())
        try:cursor=max(0,int(request.query_params.get("after_event","0")))
        except ValueError:raise HTTPException(400,"Invalid history cursor")
        return JSONResponse({"protocol_version": 1, **hub.diagnostics(), "caption_config": settings.captions.to_dict(),
                "reliability":run.health(hub,None if authority.owner_seen is None else time.monotonic()-authority.owner_seen),
                "operator_history":run.journal_snapshot(cursor),
                "translator": translator, "translator_verified": hub.last_success_sequence > 0,
                "owns_session": authority.owner == token,
                "session_open": session_open, "can_change_direction": inactive_safe(),
                "requires_stop_acknowledgement": not session_open and run.outcome == "incomplete" and not closure_acknowledged,
                "can_start": inactive_safe()},headers={"Cache-Control":"no-store"})

    @app.post("/api/operator/clear")
    async def clear_captions(request: Request):
        token = request.headers.get("x-operator-token")
        if not local_request(request, require_origin=True) or not authority.valid(token):
            raise HTTPException(403, "Local operator authorization required")
        if hub.session_id is not None and authority.owner != token:
            raise HTTPException(403, "Only the session operator may clear captions")
        try:
            data = await request.json()
            # Reading the body yields: recheck ownership immediately before mutation.
            if not authority.valid(token) or (hub.session_id is not None and authority.owner != token):
                raise HTTPException(403, "Only the current session operator may clear captions")
            if (not isinstance(data, dict) or type(data.get("visual_generation")) is not int
                    or type(data.get("protocol_version")) is not int or data["protocol_version"] != 1):
                raise ValueError("Invalid clear request")
            applied = hub.clear_captions(data.get("session_id"), data["visual_generation"])
        except (ValueError, TypeError):
            raise HTTPException(409, "Stale or invalid visual control; refresh operator status")
        return {"protocol_version": 1, "type": "captions_cleared", "applied": applied,
                "session_id": hub.session_id, "visual_generation": hub.visual_generation,
                "sequence": hub.sequence, "event_id": hub.event_id}

    @app.get("/overlay")
    async def overlay():
        return FileResponse(ROOT / "templates" / "overlay.html")

    @app.get("/overlay/preview")
    async def overlay_preview():
        return FileResponse(ROOT / "templates" / "overlay_preview.html")

    @app.get("/api/overlay/config")
    async def overlay_config(request: Request):
        try:
            return settings.captions.with_query(dict(request.query_params)).to_dict()
        except (ValueError, TypeError):
            raise HTTPException(400, "Invalid overlay configuration")

    @app.get("/api/overlay/status")
    async def overlay_status():
        return hub.diagnostics()

    @app.websocket("/ws/overlay")
    async def overlay_events(browser: WebSocket):
        await browser.accept()
        try:
            subscriber = hub.subscribe()
            run.counters["overlay_connections"]+=1
            incident("overlay","connected",hub.session_id,observer_id=subscriber.observer_id)
        except ValueError:
            await browser.close(code=1013)
            return
        send_lock = asyncio.Lock()

        async def observer_send(message):
            async with send_lock:
                await asyncio.wait_for(browser.send_json(message), 2.)

        async def send_events():
            while True:
                message = await subscriber.queue.get()
                await observer_send(message)

        async def receive_telemetry():
            while True:
                # Read-only except validated, bounded display diagnostics.
                data = await browser.receive_json()
                received_mono = time.monotonic() * 1000
                if not isinstance(data, dict):
                    continue
                if (data.get("type")=="connection_health" and not subscriber.transport
                        and data.get("session_id")==hub.session_id
                        and type(data.get("attempts")) is int and 0<=data["attempts"]<=20
                        and type(data.get("downtime_ms")) in (int,float)
                        and math.isfinite(data["downtime_ms"]) and 0<=data["downtime_ms"]<=86400000):
                    subscriber.transport={"client_reconnect_attempts":data["attempts"],"client_downtime_ms":data["downtime_ms"],"received_mono_ms":received_mono}
                    run.counters["overlay_client_reconnect_attempts"]+=data["attempts"]
                    incident("overlay","client_recovery_report",hub.session_id,observer_id=subscriber.observer_id,
                             attempts=data["attempts"],client_downtime_ms=data["downtime_ms"])
                if (data.get("type") == "clock_probe"
                        and type(data.get("client_sent_ms")) in (int, float)
                        and math.isfinite(data["client_sent_ms"])
                        and 0 <= data["client_sent_ms"] <= 1e12):
                    await observer_send({"type": "clock_sync", "protocol_version": hub.protocol_version,
                                         "client_sent_ms": data["client_sent_ms"],
                                         "server_clock_resolution_ms": time.get_clock_info("monotonic").resolution * 1000,
                                         "server_received_mono_ms": received_mono,
                                         "server_sent_mono_ms": time.monotonic() * 1000})
                if data.get("type") == "render_sample":
                    hub.record_client_sample(subscriber, data)
                if (isinstance(data, dict) and data.get("type") == "display_drop"
                        and data.get("reason") in {"queue_overflow", "oversize", "unreadable_token", "rolling_overflow"}
                        and type(data.get("count")) is int and 1 <= data["count"] <= 20000):
                    hub.report_display_drop(data.get("session_id"), data["reason"], data["count"], data.get("sequence"))

        tasks = [asyncio.create_task(send_events()), asyncio.create_task(receive_telemetry()),
                 asyncio.create_task(subscriber.closed.wait())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if tasks[0] in done and not tasks[0].cancelled() and tasks[0].exception() is not None:
                hub.broadcast_errors += 1
                logger.warning("session=%s overlay_send_failed", hub.session_id)
        finally:
            hub.unsubscribe(subscriber)
            run.counters["overlay_disconnections"]+=1
            incident("overlay","disconnected",hub.session_id,observer_id=subscriber.observer_id)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await browser.close(code=1013 if subscriber.queue.full() else 1000)
            except (RuntimeError, WebSocketDisconnect):
                pass

    @app.websocket("/ws/session")
    async def session(browser: WebSocket):
        nonlocal session_open, closure_acknowledged
        protocols = [item.strip() for item in browser.headers.get("sec-websocket-protocol", "").split(",")]
        token = protocols[1] if len(protocols) == 2 and protocols[0] == "operator.v1" else None
        if not local_request(browser, require_origin=True) or not authority.valid(token):
            await browser.close(code=4403)
            return
        values = browser.query_params.getlist("direction")
        try:
            if len(values) > 1:
                raise ValueError("Duplicate direction")
            direction = direction_from_id(values[0]) if values else None
        except ValueError:
            await browser.close(code=4400)
            return
        session_settings = (replace(settings, language=direction.source_language,
            direction=direction.to_dict(), require_language_ack=True,
            translation=replace(settings.translation, source_language=direction.source_language,
                                target_language=direction.target_language)) if direction else settings)
        if direction is None and settings.translation.source_language == settings.language:
            legacy_id = f"{settings.language}-{settings.translation.target_language}"
            if legacy_id in {"en-es", "es-en"}:
                session_settings = replace(settings, direction=direction_from_id(legacy_id).to_dict())
        await browser.accept(subprotocol="operator.v1")
        session_id = uuid4().hex[:12]
        logger.info("session=%s browser connected", session_id)
        owns_session = False
        try:
            if not authority.valid(token):
                raise ValueError("Operator authorization expired before START")
            if not inactive_safe():
                raise ValueError("An audio session is already active or its incomplete closure needs acknowledgement")
            hub.begin(session_id, direction=session_settings.direction)
            session_open = True
            closure_acknowledged = False
            owns_session = True
            authority.owner = token
            authority.owner_seen=time.monotonic()
            run.reset(session_id);run.outcome="in_progress";run.transition("RECOVERING","connecting_wlk")
            run.owner_age_getter=lambda:None if authority.owner_seen is None else time.monotonic()-authority.owner_seen
            adapter=OperatorBrowser(browser, session_id,run, direction=session_settings.direction)
            run.capture_sender=adapter.send_json
            await relay(adapter, session_settings, session_id, caption_hub=hub)
        except WebSocketDisconnect:
            if owns_session and run.session_id==session_id:
                hub.set_state(session_id, "disconnected")
                run.fail("capture_disconnected")
            logger.info("session=%s browser disconnected", session_id)
        except Exception as exc:
            if owns_session and run.session_id==session_id:
                hub.set_state(session_id, "error")
                run.fail("stop_timeout" if isinstance(exc,TimeoutError) else "resource_budget_exhausted"
                         if isinstance(exc,RuntimeError) and "budget" in str(exc).lower() else "session_transport_error")
            logger.exception("session=%s error", session_id)
            try:
                code, message = operational_error(exc)
                await browser.send_json({"type": "error", "protocol_version": 1, "session_id": session_id,
                                         "error_code": code, "message": message})
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            if owns_session and hub.state not in {"stopped", "disconnected", "error"}:
                hub.set_state(session_id, "disconnected")
            try:
                await browser.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
            finally:
                if owns_session and run.session_id==session_id:
                    run.capture_sender=None
                    session_open = False
            logger.info("session=%s session closed", session_id)

    return app


app = create_app()

import logging
import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.environment import load_project_env

load_project_env()

from app.asr.whisperlivekit_client import relay
from app.captions.segment_manager import SegmentConfig
from app.captions.terminology_normalizer import NormalizerConfig
from app.translation import TranslationConfig
from app.overlay.config import CaptionConfig
from app.overlay.hub import CaptionHub

ROOT = Path(__file__).resolve().parent


@dataclass
class Settings:
    wlk_url: str = os.getenv("WLK_WS_URL", "ws://localhost:8000/asr")
    language: str = os.getenv("CAPTIONS_LANGUAGE", "es")
    log_raw: bool = os.getenv("CAPTIONS_LOG_RAW", "0") == "1"
    log_dir: str = os.getenv("CAPTIONS_LOG_DIR", str(ROOT.parent / "logs"))
    connect_timeout: float = float(os.getenv("CAPTIONS_CONNECT_TIMEOUT", "15"))
    stop_timeout: float = float(os.getenv("CAPTIONS_STOP_TIMEOUT", "120"))
    segments: SegmentConfig = field(default_factory=SegmentConfig.from_env)
    normalizer: NormalizerConfig = field(default_factory=NormalizerConfig.from_env)
    translation: TranslationConfig = field(default_factory=TranslationConfig.from_env)
    captions: CaptionConfig = field(default_factory=CaptionConfig.from_env)


def create_app(settings=None):
    settings = settings or Settings()
    logger = logging.getLogger("captions")

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
            logger.addHandler(handler)
        raw = logging.getLogger("captions.raw")
        raw.propagate = False
        raw_handler = None
        if settings.log_raw:
            raw_handler = RotatingFileHandler(folder / "wlk-raw.log", maxBytes=10_000_000,
                                              backupCount=3, encoding="utf-8")
            raw_handler.setFormatter(formatter)
            raw.addHandler(raw_handler)
        yield
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        if raw_handler:
            raw.removeHandler(raw_handler)
            raw_handler.close()

    app = FastAPI(lifespan=lifespan)
    hub = CaptionHub(settings.captions)
    app.state.caption_hub = hub
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
        except ValueError:
            await browser.close(code=1013)
            return

        async def send_events():
            while True:
                message = await subscriber.queue.get()
                await asyncio.wait_for(browser.send_json(message), 2.)

        async def receive_telemetry():
            while True:
                # Read-only except validated, bounded display diagnostics.
                data = await browser.receive_json()
                if (isinstance(data, dict) and data.get("type") == "display_drop"
                        and data.get("reason") in {"queue_overflow", "oversize", "unreadable_token"}
                        and type(data.get("count")) is int and 1 <= data["count"] <= 256):
                    hub.report_display_drop(data.get("session_id"), data["reason"], data["count"])

        tasks = [asyncio.create_task(send_events()), asyncio.create_task(receive_telemetry()),
                 asyncio.create_task(subscriber.closed.wait())]
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if tasks[0] in done and not tasks[0].cancelled() and tasks[0].exception() is not None:
                hub.broadcast_errors += 1
                logger.warning("session=%s overlay_send_failed", hub.session_id)
        finally:
            hub.unsubscribe(subscriber)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                await browser.close(code=1013 if subscriber.queue.full() else 1000)
            except (RuntimeError, WebSocketDisconnect):
                pass

    @app.websocket("/ws/session")
    async def session(browser: WebSocket):
        await browser.accept()
        session_id = uuid4().hex[:12]
        logger.info("session=%s browser connected", session_id)
        owns_session = False
        try:
            hub.begin(session_id)
            owns_session = True
            await relay(browser, settings, session_id, caption_hub=hub)
        except WebSocketDisconnect:
            if owns_session:
                hub.set_state(session_id, "disconnected")
            logger.info("session=%s browser disconnected", session_id)
        except Exception as exc:
            if owns_session:
                hub.set_state(session_id, "error")
            logger.exception("session=%s error", session_id)
            try:
                await browser.send_json({"type": "error", "message": str(exc) or type(exc).__name__})
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            if owns_session and hub.state not in {"stopped", "disconnected", "error"}:
                hub.set_state(session_id, "disconnected")
            try:
                await browser.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
            logger.info("session=%s session closed", session_id)

    return app


app = create_app()

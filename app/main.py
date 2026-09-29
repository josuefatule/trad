import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.asr.whisperlivekit_client import relay
from app.captions.segment_manager import SegmentConfig

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

    @app.websocket("/ws/session")
    async def session(browser: WebSocket):
        await browser.accept()
        session_id = uuid4().hex[:12]
        logger.info("session=%s browser connected", session_id)
        try:
            await relay(browser, settings, session_id)
        except WebSocketDisconnect:
            logger.info("session=%s browser disconnected", session_id)
        except Exception as exc:
            logger.exception("session=%s error", session_id)
            try:
                await browser.send_json({"type": "error", "message": str(exc) or type(exc).__name__})
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            try:
                await browser.close()
            except (RuntimeError, WebSocketDisconnect):
                pass
            logger.info("session=%s session closed", session_id)

    return app


app = create_app()

"""One upstream WLK connection per browser; no model imports in this process."""
import asyncio
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

from app.captions.transcript_state import TranscriptState

logger = logging.getLogger("captions")
raw_logger = logging.getLogger("captions.raw")


def session_url(url, language):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.pop("target_language", None)
    query.update(mode="full", language=language)
    return urlunsplit(parts._replace(query=urlencode(query)))


async def relay(browser: WebSocket, settings, session_id: str):
    state = TranscriptState()

    def event(name, *args):
        logger.info("session=%s " + name, session_id, *args)

    def decode(raw):
        if settings.log_raw:
            raw_logger.info(json.dumps({"session": session_id, "raw": raw}, ensure_ascii=False))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("WLK sent a non-object JSON payload")
        event("ASR message received type=%s", payload.get("type", payload.get("status", "snapshot")))
        return payload

    await browser.send_json({"type": "status", "state": "connecting", "session_id": session_id})
    async with connect(session_url(settings.wlk_url, settings.language),
                       open_timeout=settings.connect_timeout, max_size=None,
                       proxy=None) as upstream:
        config = decode(await asyncio.wait_for(upstream.recv(), settings.connect_timeout))
        if config.get("type") != "config" or config.get("useAudioWorklet") is not True:
            raise ValueError(config.get("error") or "WLK must run with --pcm-input")
        if config.get("mode") != "full":
            raise ValueError("WLK must use full mode")
        event("wlk connected")
        await browser.send_json({"type": "config", "state": "connected", "session_id": session_id,
                                 "sample_rate": 16000, "wlk": config})

        async def upload():
            started = False
            while True:
                message = await browser.receive()
                if message["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(message.get("code", 1000))
                audio = message.get("bytes")
                if audio is None:
                    raise ValueError("Expected binary PCM audio, not text")
                if len(audio) % 2:
                    raise ValueError("PCM s16le frame must contain whole samples")
                await upstream.send(audio)
                if not audio:
                    event("audio stream ended; waiting for ready_to_stop")
                    return
                if not started:
                    event("audio stream started")
                    started = True

        async def download():
            async for raw in upstream:
                payload = decode(raw)
                if payload.get("error") or payload.get("type") == "error":
                    raise ValueError(payload.get("error", "WLK error"))
                if state.update(payload):
                    event("transcript updated segments=%d", len(state.segments))
                await browser.send_json({"type": "asr", "payload": payload, "transcript": state.to_dict()})
                if payload.get("type") == "ready_to_stop":
                    event("session stopped")
                    await browser.send_json({"type": "status", "state": "stopped"})
                    return
            raise ConnectionError("WLK disconnected before ready_to_stop")

        sender = asyncio.create_task(upload())
        receiver = asyncio.create_task(download())
        try:
            done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if sender in done:
                sender.result()
                try:
                    await asyncio.wait_for(receiver, settings.stop_timeout)
                except TimeoutError as exc:
                    raise TimeoutError("WLK finalization timed out; transcript may be incomplete") from exc
            else:
                receiver.result()
        finally:
            for task in (sender, receiver):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)

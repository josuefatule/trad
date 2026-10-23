"""One upstream WLK connection per browser; no model imports in this process."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from app.captions.transcript_state import TranscriptState
from app.captions.segment_manager import SegmentManager
from app.captions.terminology_normalizer import TerminologyNormalizer
from app.captions.identity_normalizer import IdentityNormalizer
from app.terminology.rollout import GlossaryConfig, session_normalizer
from app.translation import TranslationConfig, build_translation_engine
from app.translation.timing import TranslationTiming
from app.reliability import ReliabilityConfig, backoff, incident

logger = logging.getLogger("captions")
raw_logger = logging.getLogger("captions.raw")


def session_url(url, language):
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query.pop("target_language", None)
    query.update(mode="full", language=language)
    return urlunsplit(parts._replace(query=urlencode(query)))


@asynccontextmanager
async def starting_connection(url, settings, send, decode, run=None, sleep=asyncio.sleep):
    reliability=getattr(settings,"reliability",None) or ReliabilityConfig()
    upstream=None
    for attempt in range(reliability.connect_attempts):
        if run and run.stop_requested_at is not None:raise ConnectionError("WLK startup cancelled by STOP before PCM")
        try:
            async with asyncio.timeout(settings.connect_timeout):
                upstream=await connect(url,open_timeout=settings.connect_timeout,max_size=reliability.websocket_max_bytes,
                                       close_timeout=1,proxy=None)
                config=decode(await upstream.recv())
            if config.get("type")!="config" or config.get("useAudioWorklet") is not True:
                raise ValueError(config.get("error") or "WLK must run with --pcm-input")
            if config.get("mode")!="full":raise ValueError("WLK must use full mode")
            if getattr(settings, "require_language_ack", False) and (
                    config.get("session_language_isolation") != 1 or
                    config.get("session_language") != settings.language):
                raise ValueError("WLK language isolation not verified; use the TRAD WLK entry point")
            break
        except (OSError,TimeoutError,ConnectionError,ConnectionClosed) as exc:
            if upstream:await upstream.close();upstream=None
            if attempt+1>=reliability.connect_attempts:raise ConnectionError("WLK startup attempts exhausted") from exc
            delay=backoff(attempt,reliability.backoff_seconds,reliability.backoff_max_seconds)
            if run:run.counters["wlk_reconnect_attempts"]+=1;run.transition("RECOVERING","wlk_startup_backoff")
            incident("wlk","startup_retry",getattr(run,"session_id",None),attempt=attempt+1,delay_seconds=round(delay,3))
            await send({"type":"status","state":"recovering","reason":"wlk_startup_backoff","attempt":attempt+1})
            await sleep(delay)
        except BaseException:
            if upstream:await upstream.close()
            raise
    try:
        yield upstream,config
    finally:
        if upstream:await upstream.close()


async def relay(browser: WebSocket, settings, session_id: str, caption_hub=None):
    reliability=getattr(settings,"reliability",None) or ReliabilityConfig()
    run=getattr(browser,"run",None)
    state = TranscriptState()
    manager = SegmentManager(getattr(settings, "segments", None), session_id)
    normalizer = (IdentityNormalizer() if settings.language == "en" else
                  TerminologyNormalizer.from_config(getattr(settings, "normalizer", None)))
    normalizer = session_normalizer(getattr(settings,'glossary',None) or GlossaryConfig(mode='off'),settings.language,normalizer)
    send_lock = asyncio.Lock()

    async def send_json(message):
        async with send_lock:
            await browser.send_json(message)

    async def translation_ready(result, snapshot):
        if caption_hub is not None:
            caption_hub.record_translation_status(session_id, snapshot)
            caption_hub.publish(result)
        await send_json({"type": "translation", "session_id": session_id,
                         "translation": result.to_dict(),
                         "translation_status": snapshot["status"],
                         "translation_queue_depth": snapshot["queue_depth"],
                         "translation_metrics": snapshot["metrics"]})

    translator = build_translation_engine(
        getattr(settings, "translation", None) or TranslationConfig(),
        session_id, translation_ready)
    translator.terminology_context=getattr(normalizer,'translation_context',None)
    await translator.start()
    if run:run.translator=translator
    if caption_hub is not None:
        caption_hub.translation_status_getter = translator.snapshot

    def normalize(result):
        pairs = []
        for segment in result.ready_segments:
            item = normalizer.normalize(segment.id, segment.text)
            pairs.append((segment, item, time.monotonic()))
        segments = tuple(item.to_dict() for _, item, _ in pairs)
        for segment in segments:
            event("segment normalized id=%s corrections=%d suggestions=%d processing_ms=%.3f",
                  segment["segment_id"], len(segment["corrections"]),
                  len(segment["suggestions"]), segment["processing_ms"])
        return {"segments": segments}, pairs

    async def queue_translations(pairs):
        if run and (run.ready_count>reliability.max_ready_segments or run.ready_characters>reliability.max_ready_characters):
            incident("session","budget_exhausted",session_id,"ERROR",reason="ready_history_budget",
                     ready_segments=run.ready_count,ready_characters=run.ready_characters,
                     segment_limit=reliability.max_ready_segments,character_limit=reliability.max_ready_characters)
            raise RuntimeError("READY history budget exceeded; session incomplete")
        for segment, item, normalized_completed in pairs:
            await translator.submit(
                segment.id, item.raw_text, item.normalized_text,
                asr_first_seen_at=segment.first_seen_at,
                ready_at=segment.emitted_at,
                normalization_latency_ms=item.processing_ms,
                timing=TranslationTiming(
                    asr_first_seen_mono=manager.monotonic_origin + segment.first_seen_at,
                    ready_mono=manager.monotonic_origin + segment.emitted_at,
                    normalized_completed_mono=normalized_completed))
        if caption_hub is not None:
            caption_hub.record_translation_status(session_id, translator.snapshot())

    def event(name, *args):
        logger.info("session=%s " + name, session_id, *args)

    def decode(raw):
        if settings.log_raw:
            raw_logger.info(json.dumps({"session": session_id, "raw": raw}, ensure_ascii=False))
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("WLK sent a non-object JSON payload")
        event("ASR message received type=%s", payload.get("type", payload.get("status", "snapshot")))
        if run:run.asr(payload)
        return payload

    await send_json({"type": "status", "state": "connecting", "session_id": session_id})
    try:
      async with starting_connection(session_url(settings.wlk_url,settings.language),settings,send_json,decode,run) as (upstream,config):
        event("wlk connected")
        if run:
            run.wlk_connected_at=run.clock()
            if run.counters["wlk_reconnect_attempts"]:run.counters["wlk_recoveries"]+=1
            incident("wlk","connected",session_id,attempts=run.counters["wlk_reconnect_attempts"]+1,
                     startup_duration_seconds=round(run.clock()-run.started,3))
        await send_json({"type": "config", "state": "connected", "session_id": session_id,
                         "direction": getattr(settings, "direction", None),
                         "normalization_mode": "identity" if settings.language == "en" else "spanish_glossary",
                         "glossary": {"mode": getattr(normalizer,'mode','off'),
                                      "version": getattr(getattr(normalizer,'release',None),'version',None)},
                         "sample_rate": 16000,
                         "capabilities": {
                             "terminology_normalizer": 1,
                             "translation_engine": 1,
                             "translation_provider": translator.status.provider,
                             "caption_overlay": 1,
                             "persistent_captions": 1,
                             "caption_latency": 1,
                         },
                         "translation_status": translator.status.to_dict(),
                         "wlk": config})
        if caption_hub is not None:
            caption_hub.translator_state = translator.status.state
            caption_hub.set_state(session_id, "live")

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
                await asyncio.wait_for(upstream.send(audio),reliability.websocket_send_seconds)
                if not audio:
                    if caption_hub is not None:
                        caption_hub.set_state(session_id, "draining")
                    event("audio stream ended; waiting for ready_to_stop")
                    return
                if not started:
                    event("audio stream started")
                    started = True

        async def download():
            receiving = asyncio.create_task(upstream.recv())
            try:
                while True:
                    if run and caption_hub is not None:run.health(caption_hub,run.owner_age_getter())
                    if run and not run.watchdog_stop_sent and (run.clock()-run.started>=reliability.max_session_seconds
                            or run.asr_characters>=.9*reliability.max_asr_characters
                            or run.retained_asr_characters>=.9*reliability.max_asr_characters
                            or run.source_count>=.9*reliability.max_asr_sources
                            or run.asr_messages>=.9*reliability.max_asr_events
                            or run.ready_characters>=.9*reliability.max_ready_characters
                            or run.ready_count>=.9*reliability.max_ready_segments):
                        run.watchdog_stop_sent=True
                        await run.request_stop("session_resource_budget")
                    done, _ = await asyncio.wait({receiving}, timeout=manager.config.tick_seconds)
                    if not done:
                        result = manager.tick()
                        if result.ready_segments or result.events:
                            normalization, pairs = normalize(result)
                            await send_json({"type": "segmentation",
                                             "segmentation": result.to_dict(),
                                             "normalization": normalization,
                                             "translation_queue_depth": translator.queue_depth})
                            await queue_translations(pairs)
                        continue
                    try:
                        raw = receiving.result()
                    except Exception as exc:
                        raise ConnectionError("WLK disconnected before ready_to_stop") from exc
                    payload = decode(raw)
                    if run and run.asr_messages>reliability.max_asr_events:
                        incident("session","budget_exhausted",session_id,"ERROR",reason="asr_event_budget",observed=run.asr_messages,limit=reliability.max_asr_events)
                        raise RuntimeError("ASR event budget exhausted")
                    if (len(payload.get("lines",[]))>reliability.max_asr_sources or
                            sum(len(line.get("text") or "") for line in payload.get("lines",[]))+len(payload.get("buffer_transcription") or "")>reliability.max_asr_characters):
                        incident("session","budget_exhausted",session_id,"ERROR",reason="asr_payload_budget",
                                 lines=len(payload.get("lines",[])),line_limit=reliability.max_asr_sources,
                                 characters=sum(len(line.get("text") or "") for line in payload.get("lines",[]))+len(payload.get("buffer_transcription") or ""),character_limit=reliability.max_asr_characters)
                        raise RuntimeError("ASR history budget exceeded; final transcript incomplete")
                    if payload.get("error") or payload.get("type") == "error":
                        raise ValueError(payload.get("error", "WLK error"))
                    if state.update(payload):
                        event("transcript updated segments=%d", len(state.segments))
                    final = payload.get("type") == "ready_to_stop"
                    if final and run and not run.audio_eof:
                        raise ConnectionError("WLK finalized before audio EOF; capture may be incomplete")
                    result = (manager.finish() if final else manager.update(state)
                              if "lines" in payload else manager.tick())
                    retained=sum(len(source.text) for source in manager._sources)
                    if run:run.retained_asr_characters=retained;run.source_count=len(manager._sources)
                    if retained>reliability.max_asr_characters or len(manager._sources)>reliability.max_asr_sources:
                        incident("session","budget_exhausted",session_id,"ERROR",reason="asr_retained_budget",
                                 retained_characters=retained,sources=len(manager._sources),character_limit=reliability.max_asr_characters,source_limit=reliability.max_asr_sources)
                        raise RuntimeError("Retained ASR history budget exceeded; session incomplete")
                    normalization, pairs = normalize(result)
                    await send_json({"type": "asr", "payload": payload,
                                     "transcript": state.to_dict(),
                                     "segmentation": result.to_dict(),
                                     "normalization": normalization,
                                     "translation_queue_depth": translator.queue_depth})
                    await queue_translations(pairs)
                    if settings.log_raw and "lines" in payload:
                        event("partial trace sent raw_present=%s raw_chars=%d state_chars=%d lines=%d",
                              "buffer_transcription" in payload,
                              len(payload.get("buffer_transcription") or ""),
                              len(state.partial_text), len(state.segments))
                    if final:
                        await translator.wait_idle()
                        if caption_hub is not None:
                            caption_hub.set_state(session_id, "stopped")
                        incomplete=bool(translator.metrics.failures or translator.metrics.delivery_failures or (run and run.failure_reason))
                        event("session stopped completion=%s", "incomplete" if incomplete else "complete")
                        await send_json({"type": "status", "state": "stopped",
                                         "completion":"incomplete" if incomplete else "complete",
                                         "translation_metrics": translator.metrics.to_dict()})
                        return
                    receiving = asyncio.create_task(upstream.recv())
            finally:
                if not receiving.done():
                    receiving.cancel()
                await asyncio.gather(receiving, return_exceptions=True)

        sender = asyncio.create_task(upload())
        receiver = asyncio.create_task(download())
        try:
            done, _ = await asyncio.wait({sender, receiver}, return_when=asyncio.FIRST_COMPLETED)
            if sender in done:
                sender.result()
                try:
                    await asyncio.wait_for(receiver, settings.stop_timeout)
                except TimeoutError as exc:
                    if run:run.fail("stop_timeout")
                    raise TimeoutError("WLK finalization timed out; transcript may be incomplete") from exc
            else:
                receiver.result()
        finally:
            for task in (sender, receiver):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)
    finally:
        await translator.close()
        if caption_hub is not None and caption_hub.session_id == session_id:
            caption_hub.translation_status_getter = None

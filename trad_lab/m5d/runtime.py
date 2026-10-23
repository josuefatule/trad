"""Copy-only replay controls. Live mode delegates unchanged to the M5-C2 repair."""
import os
from uuid import uuid4


def configure_environment():
    if os.environ.get("M5D_MODE", "replay") == "live":
        from trad_lab.m5c2r.runtime import configure_environment as base
    else:
        from trad_lab.m5b.runtime import configure_environment as base
    base()
    os.environ["CAPTION_MODE"] = "timed_queue"
    if os.environ.get("M5D_MODE", "replay") != "live":
        # Human-supervised LAN checks need enough time to look at laptop B.
        # Keep the original renderer and leave all live-mode timings unchanged.
        os.environ["CAPTION_MIN_DISPLAY_MS"] = "10000"
        os.environ["CAPTION_MAX_DISPLAY_MS"] = "30000"


def provider_from_config(config):
    if os.environ.get("M5D_MODE", "replay") == "live":
        from trad_lab.m5c2b.runtime import provider_from_config as original
        return original(config)
    from app.translation.engine import TranslationStatus
    if config.enabled or config.deepl_auth_key:
        raise RuntimeError("Replay must not configure a provider")
    return None, TranslationStatus("disabled", None, "PRUEBA LAN: sin ASR, micrófono ni DeepL")


def install(app):
    from trad_lab.m5c2r.runtime import install as base
    base(app)
    if os.environ.get("M5D_MODE", "replay") == "live":
        return
    from fastapi import Request, HTTPException
    from app.operator_control import local_request
    from app.translation.models import TranslationResult
    import app.translation.engine as engine
    engine.provider_from_config = provider_from_config
    hub = app.state.caption_hub
    authority = app.state.operator_authority
    replay = {"session_id": None, "index": 0}
    texts = ("[PRUEBA LAN] Subtítulos en español: conexión estable.",
             "[PRUEBA LAN] CLEAR elimina el texto visible.",
             "[PRUEBA LAN] Este texto permite comprobar OCULTAR.",
             "[PRUEBA LAN] REANUDAR presenta solamente contenido nuevo.",
             "[PRUEBA LAN] Café, presión y secuencia: 1, 2, 3.")

    class ReplayGuard:
        def __init__(self, app):
            self.app = app

        async def __call__(self, scope, receive, send):
            if scope["type"] in {"http", "websocket"} and scope["path"] in {
                    "/ws/session", "/capture", "/m5c/physical-capture"}:
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    from fastapi.responses import Response
                    await Response(status_code=403)(scope, receive, send)
                return
            await self.app(scope, receive, send)
    app.add_middleware(ReplayGuard)
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/m5c/capabilities"]

    @app.get("/m5c/capabilities")
    async def capabilities():
        return {"phase": "M5-D replay", "physical_enabled": False, "real_deepl_enabled": False,
                "translation_enabled": False, "direction": "en-es"}

    @app.post("/api/m5d/replay/{action}")
    async def command(action: str, request: Request):
        token = request.headers.get("x-operator-token")
        if not local_request(request, require_origin=True) or not authority.valid(token):
            raise HTTPException(403, "Local operator required")
        if action == "start":
            if hub.state in {"connecting", "live", "draining"}:
                raise HTTPException(409, "Session active")
            authority.owner = token
            sid = "lan-replay-" + uuid4().hex[:12]
            hub._m5c_hidden = False
            hub.begin(sid, direction={"id": "en-es", "source_language": "en", "target_language": "es"})
            hub.set_state(sid, "live")
            replay.update(session_id=sid, index=0)
        else:
            if authority.owner != token or hub.session_id != replay["session_id"] or hub.state != "live":
                raise HTTPException(409, "Current replay owner required")
            if action == "next":
                if replay["index"] >= len(texts):
                    raise HTTPException(409, "Replay exhausted; finish before a new session")
                index = replay["index"]
                replay["index"] += 1
                hub.publish(TranslationResult(session_id=hub.session_id, segment_id=f"{hub.session_id}:{index + 1}",
                    sequence=index + 1, raw_text="", normalized_text="", translated_text=texts[index],
                    provider="m5d-test-caption", success=True, error=None, attempt_count=0,
                    queued_at=0, started_at=0, completed_at=0, queue_delay_ms=0, latency_ms=0,
                    source_language="en", target_language="es"))
            elif action == "stop":
                hub.clear_captions(hub.session_id, hub.visual_generation)
                hub.set_state(hub.session_id, "stopped")
            else:
                raise HTTPException(404, "Unknown replay action")
        return {"session_id": hub.session_id, "sequence": hub.sequence, "state": hub.state,
                "visual_generation": hub.visual_generation, "replay": True}

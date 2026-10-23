"""Version-scoped WLK entry point: session-local SimulStreaming language config.

Run ONLY in .venv-wlk: python -m app.asr.wlk_server <WLK server flags>.
No installed package edits, model copies, second server or shared language mutation.
"""
from copy import copy
import json
from urllib.parse import parse_qs


def isolated_factory(original):
    def online_factory(args, asr, language=None):
        if args.backend != "faster-whisper" or args.backend_policy != "simulstreaming":
            raise ValueError("TRAD language adapter requires faster-whisper / simulstreaming")
        language = language if language is not None else args.lan
        if language not in {"en", "es"}:
            raise ValueError("TRAD ASR supports explicit en or es only")
        if not asr.cfg.tokenizer_is_multilingual or asr.cfg.task != "transcribe":
            raise ValueError("TRAD requires a multilingual transcription model")
        local = copy(asr)
        local.cfg = copy(asr.cfg)
        local.lan = local.cfg.language = language
        # In this installed policy AlignAtt reads cfg, not original_language.
        # Skip the generic SessionASRProxy; weights/encoders remain shared.
        return original(args, local, language=None)
    return online_factory


class LanguageHandshake:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "websocket" or scope["path"] != "/asr":
            return await self.app(scope, receive, send)
        values = parse_qs(scope.get("query_string", b"").decode(), keep_blank_values=True).get("language", [])
        if len(values) != 1 or values[0] not in {"en", "es"}:
            # Reject before allocating decoder state or consuming PCM.
            await send({"type": "websocket.close", "code": 4400})
            return

        async def annotated(message):
            if message["type"] == "websocket.send" and message.get("text"):
                payload = json.loads(message["text"])
                if payload.get("type") == "config":
                    payload.update(session_language=values[0], session_language_isolation=1)
                    message = {**message, "text": json.dumps(payload)}
            await send(message)
        await self.app(scope, receive, annotated)


def main():
    from importlib.metadata import version
    if version("whisperlivekit") != "0.2.26":
        raise RuntimeError("TRAD language adapter audited for WhisperLiveKit 0.2.26 only")
    from whisperlivekit import core, audio_processor, basic_server
    factory = isolated_factory(core.online_factory)
    core.online_factory = audio_processor.online_factory = factory
    basic_server.app.add_middleware(LanguageHandshake)
    basic_server.main()


if __name__ == "__main__":
    main()

"""Offline installed-WLK contract probe; run with .venv-wlk, not unittest discovery.

Uses the actual installed factory and processor with a decoder double: no model
load, audio, inference, listening server or DeepL. Demonstrates the upstream gap.
"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

from whisperlivekit import core
from whisperlivekit.simul_whisper.config import AlignAttConfig
from app.asr import wlk_server


def main():
    class Decoder:
        def __init__(self, **kwargs):
            self.cfg = kwargs["cfg"]

    asr = SimpleNamespace(cfg=AlignAttConfig(language="es", tokenizer_is_multilingual=True),
        lan="es", tokenizer=None, use_full_mlx=False, shared_model=object(),
        mlx_encoder=None, fw_encoder=None)
    args = SimpleNamespace(backend="faster-whisper", backend_policy="simulstreaming", lan="es")
    with patch("whisperlivekit.simul_whisper.backend.AlignAtt", Decoder):
        original = core.online_factory(args, asr, language="en")
        assert original.model.cfg.language == "es", "Installed factory contract changed; re-audit adapter"
        factory = wlk_server.isolated_factory(core.online_factory)
        sessions = [factory(args, asr, language=lang) for lang in ("en", "es", "en")]
        assert [s.model.cfg.language for s in sessions] == ["en", "es", "en"]
        assert asr.cfg.language == "es"
        assert len({id(s.model.cfg) for s in sessions}) == 3
        assert all(s.asr.shared_model is asr.shared_model for s in sessions)
    print("PASS installed factory gap reproduced; adapted EN/ES/EN cfg isolated, weights shared")

    # Exercise the real decode-options/tokenizer initialization, without loading
    # weights or entering AlignAtt's GPU/CIF constructor or inference methods.
    from whisperlivekit.simul_whisper.simul_whisper import AlignAtt
    model = SimpleNamespace(dims=SimpleNamespace(n_text_ctx=448),
                            decoder=SimpleNamespace(blocks=[]), num_languages=99)
    language_tokens = []
    for lang, session in zip(("en", "es", "en"), sessions):
        decoder = object.__new__(AlignAtt)
        decoder._base_init(session.model.cfg, model)
        decoder.state = SimpleNamespace()
        decoder._init_state_common(session.model.cfg)
        assert decoder.decode_options.language == decoder.tokenizer.language == lang
        language_tokens.append(decoder.tokenizer.language_token)
    assert language_tokens[0] == language_tokens[2] != language_tokens[1]
    print("PASS actual decoder options and tokenizer language tokens: EN/ES/EN")

    sys.argv = ["trad-wlk", "--backend", "faster-whisper", "--model", "small", "--lan", "es",
                "--pcm-input", "--host", "localhost", "--port", "8000"]
    with patch("uvicorn.run") as run:
        wlk_server.main()
        run.assert_called_once()
        assert run.call_args.kwargs["host"] == "localhost"
        assert run.call_args.kwargs["port"] == 8000
        from whisperlivekit import audio_processor, basic_server
        assert core.online_factory is audio_processor.online_factory
        assert any(m.cls is wlk_server.LanguageHandshake for m in basic_server.app.user_middleware)
    print("PASS entry point wiring (uvicorn mocked); banner above is not a running server")


if __name__ == "__main__":
    main()

"""Local operator authorization and safe UI projections; no audio/provider policy."""
from dataclasses import asdict, dataclass
import ipaddress
import math
import os
import secrets
import time
from urllib.parse import urlsplit


def local_request(request, *, require_origin=False):
    try:
        if not request.client or not ipaddress.ip_address(request.client.host).is_loopback:
            return False
        host = urlsplit("http://" + request.headers.get("host", ""))
        if host.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return False
        origin = request.headers.get("origin")
        if not origin:
            return not require_origin and request.headers.get("sec-fetch-site") != "cross-site"
        origin = urlsplit(origin)
        scheme = "https" if request.url.scheme in {"https", "wss"} else "http"
        return (origin.scheme == scheme and origin.hostname == host.hostname
                and (origin.port or (443 if scheme == "https" else 80)) == (host.port or (443 if scheme == "https" else 80)))
    except ValueError:
        return False


class OperatorAuthority:
    def __init__(self):
        self.tokens = {}
        self.owner = None

    def issue(self):
        now = time.monotonic()
        self.tokens = {key: expiry for key, expiry in self.tokens.items() if expiry > now}
        if len(self.tokens) >= 64:
            raise ValueError("Too many local operator tabs")
        token = secrets.token_urlsafe(32)
        self.tokens[token] = now + 86400
        return token

    def valid(self, token):
        return isinstance(token, str) and self.tokens.get(token, 0) > time.monotonic()


@dataclass(frozen=True)
class OperatorConfig:
    poll_seconds: float = 2.
    sustained_seconds: float = 6.
    queue_depth_warning: int = 3
    queue_delay_warning_ms: float = 1000.
    render_warning_ms: float = 500.
    minimum_samples: int = 5

    def __post_init__(self):
        for key, (low, high) in {"poll_seconds": (1, 10), "sustained_seconds": (2, 120),
                "queue_depth_warning": (1, 1000), "queue_delay_warning_ms": (100, 120000),
                "render_warning_ms": (50, 30000), "minimum_samples": (3, 128)}.items():
            value = getattr(self, key)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid operator setting: {key}")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(**{key: type(value)(os.getenv("OPERATOR_" + key.upper(), value))
                      for key, value in asdict(defaults).items()})


def operational_error(error):
    text = str(error).lower()
    if "already active" in text:
        return "session_active", "Ya hay una sesión activa; no se abrió otro micrófono."
    if "401" in text or "403" in text or "authorization" in text:
        return "translation_auth", "DeepL rechazó la autenticación. Revisa la clave y reinicia FastAPI después de corregirla."
    if "translation_timeout" in text:
        return "translation_timeout", "Timeout de traducción; este segmento no se tradujo. Revisa los diagnósticos."
    if "translation_queue_full" in text:
        return "translation_queue_full", "Cola de traducción saturada; este segmento no se tradujo."
    if "pcm-input" in text or "full mode" in text:
        return "wlk_mode", "WLK incompatible: necesita --pcm-input y modo full."
    if "wlk" in text or isinstance(error, (ConnectionError, OSError, TimeoutError)):
        return "wlk_disconnected", "WLK desconectado o no disponible. Comprueba el servidor y vuelve a iniciar la sesión."
    return "session_error", "La sesión no pudo continuar. Revisa los logs locales y vuelve a iniciar cuando se resuelva el error."


class OperatorBrowser:
    """Relay adapter: annotate protocol and sanitize errors without changing results upstream."""
    def __init__(self, socket, session_id):
        self.socket = socket
        self.session_id = session_id

    async def receive(self):
        return await self.socket.receive()

    async def send_json(self, data):
        data = {**data, "protocol_version": 1, "session_id": self.session_id}
        if data.get("type") == "config":
            data["capabilities"] = {**data["capabilities"], "operator_console": 1, "captions_clear": 1}
        if data.get("type") == "translation" and data["translation"].get("error"):
            code, message = operational_error(data["translation"]["error"])
            data["translation"] = {**data["translation"], "error": message, "error_code": code}
        await self.socket.send_json(data)

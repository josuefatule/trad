"""Translation provider boundary and isolated provider implementations."""
from abc import ABC, abstractmethod
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from .models import TranslationRequest

# A cancelled asyncio waiter cannot kill urllib's running socket. One worker and
# a finite socket timeout bound that cost; queued cancelled futures never run.
_HTTP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="captions-http")
_HTTP_SLOT = threading.BoundedSemaphore(1)


class ProviderBusyError(RuntimeError):
    """Previous bounded HTTP socket still in flight; no new HTTP was issued."""


class TranslatorProvider(ABC):
    name = "abstract"

    @abstractmethod
    async def translate(self, request: TranslationRequest) -> str:
        """Return only the translation of request.normalized_text."""


class MockTranslatorProvider(TranslatorProvider):
    """Deterministic development provider; deliberately labelled as mock output."""

    name = "mock"

    def __init__(self, *, latency_seconds=0., failures=None):
        self.latency_seconds = latency_seconds
        self.failures = dict(failures or {})
        self.requests = []

    async def translate(self, request):
        self.requests.append(request)
        if self.latency_seconds:
            await asyncio.sleep(self.latency_seconds)
        remaining = self.failures.get(request.segment_id, 0)
        if remaining:
            self.failures[request.segment_id] = remaining - 1
            raise RuntimeError(f"mock failure for {request.segment_id}")
        return f"[MOCK {request.target_language.upper()}] {request.normalized_text}"


class DeepLTranslatorProvider(TranslatorProvider):
    """DeepL adapter. Context is sent separately and is not part of translated text."""

    name = "deepl"

    def __init__(self, auth_key, api_url="https://api-free.deepl.com/v2/translate",
                 request_timeout=10., opener=urlopen):
        if not auth_key:
            raise ValueError("DEEPL_AUTH_KEY is required")
        self.auth_key = auth_key
        self.api_url = api_url
        self.request_timeout = request_timeout
        self._opener = opener

    async def translate(self, request):
        body = {
            "text": [request.normalized_text],
            "source_lang": request.source_language.upper(),
            "target_lang": request.target_language.upper(),
        }
        context = " ".join(item.normalized_text for item in request.context_segments).strip()
        if request.terminology_context:
            context = "\n\n".join(part for part in (context,request.terminology_context) if part)
        if context:
            body["context"] = context
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        http_request = Request(
            self.api_url,
            data=encoded,
            headers={
                "Authorization": f"DeepL-Auth-Key {self.auth_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        def perform():
            try:
                with self._opener(http_request, timeout=self.request_timeout) as response:
                    data=response.read(1000001)
                    if len(data)>1000000:raise ValueError("Provider response exceeds operational budget")
                    return json.loads(data.decode("utf-8"))
            finally:_HTTP_SLOT.release()

        if not _HTTP_SLOT.acquire(blocking=False):raise ProviderBusyError("provider_http_busy")
        try:future=asyncio.get_running_loop().run_in_executor(_HTTP_EXECUTOR, perform)
        except BaseException:_HTTP_SLOT.release();raise
        # The socket owns the slot until it returns, even if the session stops.
        # Socket operations have a timeout; cancellation cannot kill a thread.
        # No executor queue accumulates across sessions.
        future.add_done_callback(lambda done:None if done.cancelled() else done.exception())
        payload = await asyncio.shield(future)
        try:
            translated = payload["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("DeepL returned an invalid translation response") from exc
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("DeepL returned an empty translation")
        return translated

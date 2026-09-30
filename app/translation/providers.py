"""Translation provider boundary and isolated provider implementations."""
from abc import ABC, abstractmethod
import asyncio
import json
from urllib.request import Request, urlopen

from .models import TranslationRequest


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
            with self._opener(http_request, timeout=self.request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))

        payload = await asyncio.to_thread(perform)
        try:
            translated = payload["translations"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("DeepL returned an invalid translation response") from exc
        if not isinstance(translated, str) or not translated.strip():
            raise ValueError("DeepL returned an empty translation")
        return translated

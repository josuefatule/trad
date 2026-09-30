"""Sequential non-blocking translation queue with context, retries and ordering."""
import asyncio
from collections import deque
from dataclasses import asdict, dataclass
import logging
import math
import os
import time

from .models import TranslationContextSegment, TranslationRequest, TranslationResult
from .providers import DeepLTranslatorProvider, MockTranslatorProvider

logger = logging.getLogger("captions")


def _env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class TranslationConfig:
    enabled: bool = False
    provider: str = ""
    source_language: str = "es"
    target_language: str = "en"
    context_segments: int = 2
    timeout_seconds: float = 8.
    retries: int = 1
    queue_maxsize: int = 32
    deepl_auth_key: str = ""
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"

    def __post_init__(self):
        if self.context_segments < 0:
            raise ValueError("context_segments cannot be negative")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")
        if self.queue_maxsize < 1:
            raise ValueError("queue_maxsize must be positive")
        if not self.source_language.strip() or not self.target_language.strip():
            raise ValueError("translation languages cannot be empty")

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            enabled=_env_bool("TRANSLATION_ENABLED", defaults.enabled),
            provider=os.getenv("TRANSLATION_PROVIDER", defaults.provider).strip().lower(),
            source_language=os.getenv("TRANSLATION_SOURCE_LANGUAGE", defaults.source_language),
            target_language=os.getenv("TRANSLATION_TARGET_LANGUAGE", defaults.target_language),
            context_segments=int(os.getenv("TRANSLATION_CONTEXT_SEGMENTS", defaults.context_segments)),
            timeout_seconds=float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", defaults.timeout_seconds)),
            retries=int(os.getenv("TRANSLATION_RETRIES", defaults.retries)),
            queue_maxsize=int(os.getenv("TRANSLATION_QUEUE_MAXSIZE", defaults.queue_maxsize)),
            deepl_auth_key=os.getenv("DEEPL_AUTH_KEY", ""),
            deepl_api_url=os.getenv("DEEPL_API_URL", defaults.deepl_api_url),
        )


@dataclass(frozen=True)
class TranslationStatus:
    state: str
    provider: str | None
    message: str

    def to_dict(self):
        return asdict(self)


@dataclass
class TranslationMetrics:
    queued: int = 0
    successes: int = 0
    failures: int = 0
    retries: int = 0
    timeouts: int = 0
    stale_discarded: int = 0
    max_queue_depth: int = 0

    def to_dict(self):
        return asdict(self)


def provider_from_config(config):
    if not config.enabled:
        return None, TranslationStatus("disabled", config.provider or None,
                                       "Translation is disabled")
    if not config.provider:
        return None, TranslationStatus("misconfigured", None,
                                       "TRANSLATION_PROVIDER is required")
    if config.provider == "mock":
        return MockTranslatorProvider(), TranslationStatus("ready", "mock",
                                                            "Deterministic mock provider")
    if config.provider == "deepl":
        if not config.deepl_auth_key:
            return None, TranslationStatus("misconfigured", "deepl",
                                           "DEEPL_AUTH_KEY is required")
        provider = DeepLTranslatorProvider(
            config.deepl_auth_key, config.deepl_api_url, config.timeout_seconds)
        return provider, TranslationStatus("ready", "deepl", "DeepL provider ready")
    return None, TranslationStatus("misconfigured", config.provider,
                                   f"Unknown translation provider: {config.provider}")


class TranslationEngine:
    def __init__(self, config, provider, session_id, on_result=None, *, status=None):
        self.config = config
        self.provider = provider
        self.session_id = session_id
        self.on_result = on_result
        self.status = status or TranslationStatus(
            "ready" if provider else "disabled", getattr(provider, "name", None), "")
        self.metrics = TranslationMetrics()
        self._generation = 0
        self._workers = set()
        self._worker = None
        self._queue = None
        self._context = deque(maxlen=config.context_segments or None)
        self._next_sequence = 1
        self._next_emit = 1
        self._completed = {}
        self._emit_lock = asyncio.Lock()

    @property
    def queue_depth(self):
        return self._queue.qsize() if self._queue is not None else 0

    def snapshot(self):
        return {"status": self.status.to_dict(), "queue_depth": self.queue_depth,
                "metrics": self.metrics.to_dict()}

    async def start(self):
        if self.provider is not None and self._worker is None:
            self._queue = asyncio.Queue(maxsize=self.config.queue_maxsize)
            self._start_worker()
        logger.info("session=%s translation_engine_reset provider=%s state=%s",
                    self.session_id, self.status.provider, self.status.state)

    def _start_worker(self):
        generation = self._generation
        worker = asyncio.create_task(self._run(generation))
        self._worker = worker
        self._workers.add(worker)
        worker.add_done_callback(self._workers.discard)

    async def reset(self, session_id):
        self._generation += 1
        previous = self._worker
        if previous and not previous.done():
            previous.cancel()
        self.session_id = session_id
        self.metrics = TranslationMetrics()
        self._context = deque(maxlen=self.config.context_segments or None)
        self._next_sequence = 1
        self._next_emit = 1
        self._completed = {}
        self._queue = asyncio.Queue(maxsize=self.config.queue_maxsize) if self.provider else None
        self._worker = None
        if self.provider:
            self._start_worker()
        logger.info("session=%s translation_engine_reset provider=%s state=%s",
                    session_id, self.status.provider, self.status.state)

    async def close(self):
        for worker in tuple(self._workers):
            if not worker.done():
                worker.cancel()
        if self._workers:
            await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        self._worker = None

    async def wait_idle(self):
        if self._queue is not None:
            await self._queue.join()

    async def submit(self, segment_id, raw_text, normalized_text, *,
                     asr_first_seen_at=None, ready_at=None, normalization_latency_ms=None):
        if self.provider is None:
            return None
        sequence = self._next_sequence
        self._next_sequence += 1
        context = tuple(self._context) if self.config.context_segments else ()
        now = time.time()
        request = TranslationRequest(
            session_id=self.session_id,
            segment_id=str(segment_id),
            sequence=sequence,
            raw_text=raw_text,
            normalized_text=normalized_text,
            context_segments=context,
            source_language=self.config.source_language,
            target_language=self.config.target_language,
            queued_at=now,
            asr_first_seen_at=asr_first_seen_at,
            ready_at=ready_at,
            normalization_latency_ms=normalization_latency_ms,
        )
        if not isinstance(normalized_text, str) or not normalized_text.strip():
            result = self._failure(request, "invalid_segment: normalized_text is empty", 0, now, now)
            await self._store_result(result, self._generation)
            return request
        self._context.append(TranslationContextSegment(segment_id, sequence, normalized_text))
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            result = self._failure(request, "translation_queue_full", 0, now, now)
            await self._store_result(result, self._generation)
            return request
        self.metrics.queued += 1
        depth = self.queue_depth
        self.metrics.max_queue_depth = max(self.metrics.max_queue_depth, depth)
        logger.info("session=%s translation_queued segment_id=%s sequence=%d translation_queue_depth=%d",
                    self.session_id, segment_id, sequence, depth)
        return request

    async def _run(self, generation):
        queue = self._queue
        while True:
            request = await queue.get()
            try:
                result = await self._translate(request)
                await self._store_result(result, generation)
            finally:
                queue.task_done()

    async def _translate(self, request):
        started_wall = time.time()
        started_mono = time.monotonic()
        queue_delay = max(0., (started_wall - request.queued_at) * 1000)
        logger.info("session=%s translation_started segment_id=%s sequence=%d "
                    "translation_queue_depth=%d translation_queue_delay_ms=%.3f",
                    request.session_id, request.segment_id, request.sequence,
                    self.queue_depth, queue_delay)
        error = None
        attempts = 0
        for attempt in range(1, self.config.retries + 2):
            attempts = attempt
            try:
                translated = await asyncio.wait_for(
                    self.provider.translate(request), self.config.timeout_seconds)
                if not isinstance(translated, str) or not translated.strip():
                    raise ValueError("provider returned empty translation")
                completed = time.time()
                latency = max(0., (time.monotonic() - started_mono) * 1000)
                result = TranslationResult(
                    request.session_id, request.segment_id, request.sequence,
                    request.raw_text, request.normalized_text, translated,
                    self.provider.name, True, None, attempts, request.queued_at,
                    started_wall, completed, round(queue_delay, 3), round(latency, 3),
                    request.asr_first_seen_at, request.ready_at,
                    request.normalization_latency_ms)
                logger.info("session=%s translation_completed segment_id=%s sequence=%d "
                            "attempt_count=%d latency_ms=%.3f",
                            request.session_id, request.segment_id, request.sequence,
                            attempts, latency)
                return result
            except TimeoutError:
                self.metrics.timeouts += 1
                error = f"translation_timeout after {self.config.timeout_seconds:g}s"
                logger.warning("session=%s translation_timeout segment_id=%s sequence=%d attempt=%d",
                               request.session_id, request.segment_id, request.sequence, attempt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            if attempt <= self.config.retries:
                self.metrics.retries += 1
                logger.warning("session=%s translation_retry segment_id=%s sequence=%d attempt=%d error=%s",
                               request.session_id, request.segment_id, request.sequence, attempt, error)
        completed = time.time()
        latency = max(0., (time.monotonic() - started_mono) * 1000)
        result = self._failure(request, error or "translation failed", attempts,
                               started_wall, completed, queue_delay, latency)
        logger.error("session=%s translation_failed segment_id=%s sequence=%d attempt_count=%d error=%s",
                     request.session_id, request.segment_id, request.sequence, attempts, error)
        return result

    def _failure(self, request, error, attempts, started, completed,
                 queue_delay=0., latency=0.):
        return TranslationResult(
            request.session_id, request.segment_id, request.sequence,
            request.raw_text, request.normalized_text, None,
            getattr(self.provider, "name", self.status.provider or "none"),
            False, error, attempts, request.queued_at, started, completed,
            round(queue_delay, 3), round(latency, 3), request.asr_first_seen_at,
            request.ready_at, request.normalization_latency_ms)

    async def _store_result(self, result, generation):
        if generation != self._generation or result.session_id != self.session_id:
            self.metrics.stale_discarded += 1
            logger.warning("session=%s translation_discarded_stale_session segment_id=%s result_session=%s",
                           self.session_id, result.segment_id, result.session_id)
            return
        async with self._emit_lock:
            self._completed[result.sequence] = result
            while self._next_emit in self._completed:
                ready = self._completed.pop(self._next_emit)
                self._next_emit += 1
                if ready.success:
                    self.metrics.successes += 1
                else:
                    self.metrics.failures += 1
                if self.on_result is not None:
                    try:
                        await self.on_result(ready, self.snapshot())
                    except Exception:
                        logger.exception("session=%s translation result callback failed segment_id=%s",
                                         self.session_id, ready.segment_id)


def build_translation_engine(config, session_id, on_result=None):
    provider, status = provider_from_config(config)
    return TranslationEngine(config, provider, session_id, on_result, status=status)

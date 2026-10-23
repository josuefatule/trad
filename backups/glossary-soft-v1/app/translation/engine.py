"""Sequential non-blocking translation queue with context, retries and ordering."""
import asyncio
from collections import deque
from dataclasses import asdict, dataclass, field, replace
import logging
import math
import os
import time
from urllib.error import HTTPError
from app.reliability import backoff, incident

from .models import TranslationContextSegment, TranslationRequest, TranslationResult
from .providers import DeepLTranslatorProvider, MockTranslatorProvider, ProviderBusyError
from .timing import TranslationTiming, elapsed_ms

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
    retry_backoff_seconds: float = .25
    retry_backoff_max_seconds: float = 2.
    request_deadline_seconds: float = 20.
    max_queue_age_seconds: float = 30.
    max_pending_results: int = 128
    deepl_auth_key: str = field(default="", repr=False)
    deepl_api_url: str = "https://api-free.deepl.com/v2/translate"

    def __post_init__(self):
        if self.context_segments < 0:
            raise ValueError("context_segments cannot be negative")
        if not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 60:
            raise ValueError("timeout_seconds must be finite and positive")
        if self.retries < 0:
            raise ValueError("retries cannot be negative")
        if self.queue_maxsize < 1:
            raise ValueError("queue_maxsize must be positive")
        if self.retries > 5 or self.queue_maxsize > 256 or self.context_segments > 16:
            raise ValueError("Translation configuration exceeds operational bounds")
        for name in ("retry_backoff_seconds", "retry_backoff_max_seconds", "request_deadline_seconds", "max_queue_age_seconds"):
            if not math.isfinite(getattr(self,name)) or getattr(self,name)<=0:
                raise ValueError(f"Invalid translation setting: {name}")
        if not 2 <= self.max_pending_results <= 4096:
            raise ValueError("Invalid pending result limit")
        if self.request_deadline_seconds>120 or self.max_queue_age_seconds>600:
            raise ValueError("Translation deadline/queue age exceeds operational bounds")
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
            **{name:type(getattr(defaults,name))(os.getenv("TRANSLATION_"+name.upper(),getattr(defaults,name)))
               for name in ("retry_backoff_seconds","retry_backoff_max_seconds","request_deadline_seconds","max_queue_age_seconds","max_pending_results")},
            deepl_auth_key=os.getenv("DEEPL_API_KEY") or os.getenv("DEEPL_AUTH_KEY", ""),
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
    permanent_errors: int = 0
    cancelled: int = 0
    expired: int = 0
    possible_duplicate_requests: int = 0
    delivery_failures: int = 0

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
                                           "DEEPL_API_KEY (or DEEPL_AUTH_KEY) is required")
        provider = DeepLTranslatorProvider(
            config.deepl_auth_key, config.deepl_api_url, min(config.timeout_seconds,config.request_deadline_seconds))
        return provider, TranslationStatus("ready", "deepl", "DeepL provider ready")
    return None, TranslationStatus("misconfigured", config.provider,
                                   f"Unknown translation provider: {config.provider}")


class TranslationEngine:
    def __init__(self, config, provider, session_id, on_result=None, *, status=None,
                 monotonic_clock=time.monotonic, sleep=asyncio.sleep, jitter=None):
        self.config = config
        self.provider = provider
        self.session_id = session_id
        self.on_result = on_result
        self.status = status or TranslationStatus(
            "ready" if provider else "disabled", getattr(provider, "name", None), "")
        self._clock = monotonic_clock
        self._sleep = sleep
        self._jitter=jitter
        self.health="READY" if provider else "ERROR" if self.status.state=="misconfigured" else "DISCONNECTED"
        self.last_seen=None;self.last_error=None;self._permanent_error=None;self._cooldown_until=0.
        self._active_request=None
        self.metrics = TranslationMetrics()
        self._generation = 0
        self._workers = set()
        self._worker = None
        self._queue = None
        self._context = deque(maxlen=config.context_segments)
        self._next_sequence = 1
        self._next_emit = 1
        self._completed = {}
        self._emit_lock = asyncio.Lock()

    @property
    def queue_depth(self):
        return self._queue.qsize() if self._queue is not None else 0

    def snapshot(self):
        status=self.status.to_dict()
        if self.provider and self.health in {"ERROR","DEGRADED","RECOVERING"}:
            status.update(state=self.health.lower(),message=self.last_error or "Awaiting a successful translation")
        return {"status": status, "queue_depth": self.queue_depth,
                "health":self.health,"last_seen_mono":self.last_seen,"reason":self.last_error,
                "pending_count":self.pending_count,"cooldown_remaining_seconds":max(0,self._cooldown_until-self._clock()),
                "metrics": self.metrics.to_dict()}

    @property
    def pending_count(self):
        return self._next_sequence-self._next_emit

    def rearm(self):
        if self.provider is None:return False
        self._permanent_error=None;self._cooldown_until=0.;self.health="RECOVERING";self.last_error=None
        incident("translator","manual_rearm",self.session_id)
        return True

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
        self._context = deque(maxlen=self.config.context_segments)
        self._permanent_error=None;self._cooldown_until=0.;self.health="READY" if self.provider else "ERROR" if self.status.state=="misconfigured" else "DISCONNECTED"
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
        pending=self.pending_count
        if pending:
            self.metrics.cancelled+=pending
            incident("translator","cancelled_range",self.session_id,"WARNING",
                     first_sequence=self._next_emit,last_sequence=self._next_sequence-1,count=pending,
                     active_segment_id=getattr(self._active_request,"segment_id",None),
                     possible_in_flight_charge=self._active_request is not None)
        self._generation+=1
        for worker in tuple(self._workers):
            if not worker.done():
                worker.cancel()
        if self._workers:
            await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        self._worker = None
        self._completed.clear();self._context.clear();self._queue=None;self._active_request=None
        self._next_emit=self._next_sequence

    async def wait_idle(self):
        if self._queue is not None:
            await self._queue.join()

    async def submit(self, segment_id, raw_text, normalized_text, *,
                     asr_first_seen_at=None, ready_at=None, normalization_latency_ms=None,
                     timing=None):
        if self.provider is None:
            return None
        if self.pending_count >= self.config.max_pending_results:
            incident("translator","pending_budget_exhausted",self.session_id,"ERROR",segment_id=str(segment_id),pending_count=self.pending_count)
            raise RuntimeError("translation_pending_budget_exhausted")
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
            timing=replace(timing or TranslationTiming(), queued_mono=self._clock()),
        )
        if not isinstance(normalized_text, str) or not normalized_text.strip():
            result = self._failure(request, "invalid_segment: normalized_text is empty", 0, now, now)
            await self._store_result(result, self._generation)
            return request
        self._context.append(TranslationContextSegment(segment_id, sequence, normalized_text))
        try:
            self._queue.put_nowait(request)
        except asyncio.QueueFull:
            incident("translator","queue_rejected",self.session_id,"ERROR",segment_id=str(segment_id),sequence=sequence)
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
                self._active_request=request
                result = await self._translate(request)
                await self._store_result(result, generation)
            finally:
                self._active_request=None
                queue.task_done()

    async def _translate(self, request):
        started_wall = time.time()
        started_mono = self._clock()
        timing = replace(request.timing or TranslationTiming(), translation_started_mono=started_mono)
        queue_delay = elapsed_ms(timing.queued_mono, started_mono) or 0.
        logger.info("session=%s translation_started segment_id=%s sequence=%d "
                    "translation_queue_depth=%d translation_queue_delay_ms=%.3f",
                    request.session_id, request.segment_id, request.sequence,
                    self.queue_depth, queue_delay)
        error = None
        attempts = 0
        attempt_durations = []
        if queue_delay > self.config.max_queue_age_seconds*1000:
            self.metrics.expired+=1
            self.health="DEGRADED";self.last_error="translation_queue_expired"
            incident("translator","queue_expired",self.session_id,"ERROR",segment_id=request.segment_id,sequence=request.sequence,queue_delay_ms=queue_delay)
            return self._failure(request,self.last_error,0,started_wall,time.time(),queue_delay)
        if self._permanent_error or self._clock()<self._cooldown_until:
            reason=self._permanent_error or "provider_cooldown"
            incident("translator","request_not_sent",self.session_id,"ERROR",segment_id=request.segment_id,sequence=request.sequence,reason=reason)
            return self._failure(request,reason,0,started_wall,time.time(),queue_delay)
        deadline=started_mono+self.config.request_deadline_seconds
        for attempt in range(1, self.config.retries + 2):
            if self._clock()>=deadline:break
            attempts = attempt
            attempt_started = self._clock()
            try:
                translated = await asyncio.wait_for(
                    self.provider.translate(request), min(self.config.timeout_seconds,max(.001,deadline-self._clock())))
                if not isinstance(translated, str) or not translated.strip():
                    raise ValueError("provider returned empty translation")
                completed = time.time()
                completed_mono = self._clock()
                attempt_durations.append(elapsed_ms(attempt_started, completed_mono))
                timing = replace(timing, translation_completed_mono=completed_mono,
                                 provider_attempts_ms=tuple(attempt_durations))
                latency = elapsed_ms(started_mono, completed_mono)
                result = TranslationResult(
                    request.session_id, request.segment_id, request.sequence,
                    request.raw_text, request.normalized_text, translated,
                    self.provider.name, True, None, attempts, request.queued_at,
                    started_wall, completed, round(queue_delay, 3), round(latency, 3),
                    request.asr_first_seen_at, request.ready_at,
                    request.normalization_latency_ms, timing,
                    request.source_language, request.target_language)
                logger.info("session=%s translation_completed segment_id=%s sequence=%d "
                            "attempt_count=%d latency_ms=%.3f",
                            request.session_id, request.segment_id, request.sequence,
                            attempts, latency)
                self.last_seen=completed_mono;self.health="READY";self.last_error=None
                return result
            except TimeoutError:
                attempt_durations.append(elapsed_ms(attempt_started, self._clock()))
                self.metrics.timeouts += 1
                error = f"translation_timeout after {self.config.timeout_seconds:g}s"
                code="translation_timeout";retryable=True;retry_after=0.
                logger.warning("session=%s translation_timeout segment_id=%s sequence=%d attempt=%d",
                               request.session_id, request.segment_id, request.sequence, attempt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                attempt_durations.append(elapsed_ms(attempt_started, self._clock()))
                status=getattr(exc,"code",None) if isinstance(exc,HTTPError) else None
                code=("provider_auth" if status in {401,403} else "provider_quota" if status==456 else
                      f"provider_http_{status}" if status else "provider_busy" if isinstance(exc,ProviderBusyError) else "provider_invalid_response" if isinstance(exc,ValueError) else "provider_network")
                retryable=status==429 or (status is not None and status>=500) or (status is None and not isinstance(exc,ValueError))
                retry_after=0.
                if status==429:
                    try:retry_after=max(0.,float(exc.headers.get("Retry-After","0")))
                    except (ValueError,AttributeError):pass
                if isinstance(exc,HTTPError) and exc.fp is not None:exc.close()
                error=code
                if status in {401,403,456}:
                    self._permanent_error=code;self.metrics.permanent_errors+=1
                incident("translator","attempt_failed",self.session_id,"WARNING",segment_id=request.segment_id,
                         sequence=request.sequence,attempt=attempt,reason=code,retryable=retryable)
            self.last_seen=self._clock();self.last_error=code;self.health="ERROR" if self._permanent_error else "DEGRADED"
            delay=max(retry_after,backoff(attempt-1,self.config.retry_backoff_seconds,self.config.retry_backoff_max_seconds,
                                        self._jitter() if self._jitter else None))
            if code=="provider_http_429":
                self._cooldown_until=self._clock()+delay
            if retryable and attempt <= self.config.retries:
                self._cooldown_until=self._clock()+delay
                if self._cooldown_until>=deadline:break
                self.metrics.retries += 1
                if code in {"translation_timeout","provider_network"}:
                    self.metrics.possible_duplicate_requests+=1
                    incident("translator","retry_may_repeat_billable_request",self.session_id,"WARNING",segment_id=request.segment_id,sequence=request.sequence)
                logger.warning("session=%s translation_retry segment_id=%s sequence=%d attempt=%d error=%s",
                               request.session_id, request.segment_id, request.sequence, attempt, error)
                self.health="RECOVERING"
                await self._sleep(delay)
            else:break
        completed = time.time()
        latency = max(0., (self._clock() - started_mono) * 1000)
        result = self._failure(request, error or "translation failed", attempts,
                               started_wall, completed, queue_delay, latency)
        result = replace(result, timing=replace(timing,
                         translation_completed_mono=self._clock(),
                         provider_attempts_ms=tuple(attempt_durations)))
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
            request.ready_at, request.normalization_latency_ms,
            replace(request.timing or TranslationTiming(), translation_completed_mono=self._clock()),
            request.source_language, request.target_language)

    async def _store_result(self, result, generation):
        if generation != self._generation or result.session_id != self.session_id:
            self.metrics.stale_discarded += 1
            logger.warning("session=%s translation_discarded_stale_session segment_id=%s result_session=%s",
                           self.session_id, result.segment_id, result.session_id)
            return
        async with self._emit_lock:
            if result.sequence<self._next_emit or result.sequence in self._completed:return
            self._completed[result.sequence] = result
            while self._next_emit in self._completed:
                ready = self._completed.pop(self._next_emit)
                self._next_emit += 1
                if ready.success:
                    self.metrics.successes += 1
                else:
                    self.metrics.failures += 1
                    if self.health!="ERROR":self.health="DEGRADED";self.last_error=ready.error
                if self.on_result is not None:
                    try:
                        await self.on_result(ready, self.snapshot())
                    except Exception:
                        self.metrics.delivery_failures+=1;self.health="DEGRADED";self.last_error="result_delivery_failed"
                        incident("translator","result_delivery_failed",self.session_id,"ERROR",segment_id=ready.segment_id,sequence=ready.sequence)
                        logger.exception("session=%s translation result callback failed segment_id=%s",
                                         self.session_id, ready.segment_id)


def build_translation_engine(config, session_id, on_result=None):
    provider, status = provider_from_config(config)
    return TranslationEngine(config, provider, session_id, on_result, status=status)

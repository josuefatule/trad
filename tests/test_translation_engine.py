"""Milestone 4 translation contracts; no network, microphone or real sleeps."""
import asyncio
from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from app.translation import (
    DeepLTranslatorProvider,
    MockTranslatorProvider,
    TranslationConfig,
    TranslationContextSegment,
    TranslationEngine,
    TranslationRequest,
    TranslatorProvider,
    build_translation_engine,
)
from replay_fixture import async_main


class EchoProvider(TranslatorProvider):
    name = "echo-test"

    def __init__(self, fail_ids=()):
        self.requests = []
        self.fail_ids = set(fail_ids)

    async def translate(self, request):
        self.requests.append(request)
        if request.segment_id in self.fail_ids:
            raise RuntimeError("controlled failure")
        return f"EN:{request.normalized_text}"


class PlannedProvider(TranslatorProvider):
    name = "planned-test"

    def __init__(self, actions):
        self.actions = list(actions)
        self.calls = 0

    async def translate(self, request):
        action = self.actions[self.calls]
        self.calls += 1
        if action == "timeout":
            await asyncio.Future()
        if isinstance(action, Exception):
            raise action
        return action


async def run_segments(config, provider, segments):
    results = []

    async def collect(result, snapshot):
        results.append(result)

    engine = TranslationEngine(config, provider, "session-a", collect)
    await engine.start()
    requests = []
    for segment_id, raw, normalized in segments:
        requests.append(await engine.submit(segment_id, raw, normalized))
    await engine.wait_idle()
    await engine.close()
    return engine, requests, results


class TranslationEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_provider_is_an_abstraction(self):
        with self.assertRaises(TypeError):
            TranslatorProvider()

    def test_configuration_reads_environment(self):
        values = {
            "TRANSLATION_ENABLED": "1",
            "TRANSLATION_PROVIDER": "mock",
            "TRANSLATION_SOURCE_LANGUAGE": "es",
            "TRANSLATION_TARGET_LANGUAGE": "en",
            "TRANSLATION_CONTEXT_SEGMENTS": "1",
            "TRANSLATION_TIMEOUT_SECONDS": "3.5",
            "TRANSLATION_RETRIES": "2",
            "TRANSLATION_QUEUE_MAXSIZE": "7",
        }
        with patch.dict(os.environ, values, clear=False):
            config = TranslationConfig.from_env()
        self.assertEqual((config.enabled, config.provider, config.context_segments,
                          config.timeout_seconds, config.retries, config.queue_maxsize),
                         (True, "mock", 1, 3.5, 2, 7))

    async def test_mock_is_deterministic_and_never_emits_context(self):
        config = TranslationConfig(enabled=True, provider="mock", context_segments=1)
        provider = MockTranslatorProvider()
        _, requests, results = await run_segments(config, provider, [
            ("1", "La hipertensión arterial.", "La hipertensión arterial."),
            ("2", "Puede producir daño.", "Puede producir daño."),
        ])
        self.assertEqual(results[1].translated_text, "[MOCK EN] Puede producir daño.")
        self.assertNotIn("hipertensión", results[1].translated_text)
        self.assertEqual([item.normalized_text for item in requests[1].context_segments],
                         ["La hipertensión arterial."])

    async def test_context_windows_zero_one_and_two(self):
        for size, expected in ((0, []), (1, ["dos"]), (2, ["uno", "dos"])):
            provider = EchoProvider()
            config = TranslationConfig(enabled=True, provider="test", context_segments=size)
            _, requests, _ = await run_segments(config, provider, [
                ("1", "uno", "uno"), ("2", "dos", "dos"), ("3", "tres", "tres")])
            self.assertEqual([item.normalized_text for item in requests[2].context_segments], expected)

    async def test_raw_and_normalized_are_preserved_with_unicode_and_punctuation(self):
        config = TranslationConfig(enabled=True, provider="test")
        _, _, results = await run_segments(config, EchoProvider(), [
            ("ñ", "¿Presión systólica?", "¿Presión sistólica?"),
        ])
        self.assertEqual(results[0].raw_text, "¿Presión systólica?")
        self.assertEqual(results[0].normalized_text, "¿Presión sistólica?")
        self.assertEqual(results[0].translated_text, "EN:¿Presión sistólica?")

    async def test_order_and_queue_depth_are_stable(self):
        config = TranslationConfig(enabled=True, provider="mock", queue_maxsize=8)
        provider = MockTranslatorProvider(latency_seconds=.001)
        engine, _, results = await run_segments(config, provider, [
            (str(index), str(index), str(index)) for index in range(1, 5)])
        self.assertEqual([result.sequence for result in results], [1, 2, 3, 4])
        self.assertGreaterEqual(engine.metrics.max_queue_depth, 1)
        self.assertTrue(all(result.queue_delay_ms >= 0 for result in results))

    async def test_timeout_then_retry_succeeds(self):
        config = TranslationConfig(enabled=True, provider="test", timeout_seconds=.005, retries=1)
        engine, _, results = await run_segments(
            config, PlannedProvider(["timeout", "recovered"]), [("1", "raw", "normal")])
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].translated_text, "recovered")
        self.assertEqual(results[0].attempt_count, 2)
        self.assertEqual(engine.metrics.timeouts, 1)
        self.assertEqual(engine.metrics.retries, 1)

    async def test_retry_exhausted(self):
        config = TranslationConfig(enabled=True, provider="test", timeout_seconds=.005, retries=1)
        engine, _, results = await run_segments(
            config, PlannedProvider(["timeout", "timeout"]), [("1", "raw", "normal")])
        self.assertFalse(results[0].success)
        self.assertIn("translation_timeout", results[0].error)
        self.assertEqual(engine.metrics.timeouts, 2)

    async def test_provider_exception_does_not_block_next_segment(self):
        config = TranslationConfig(enabled=True, provider="test", retries=0)
        _, _, results = await run_segments(config, EchoProvider({"bad"}), [
            ("bad", "raw one", "normal one"), ("good", "raw two", "normal two")])
        self.assertFalse(results[0].success)
        self.assertTrue(results[1].success)
        self.assertEqual([result.sequence for result in results], [1, 2])

    async def test_invalid_empty_segment_is_reported_and_not_added_to_context(self):
        config = TranslationConfig(enabled=True, provider="test", context_segments=2)
        _, requests, results = await run_segments(config, EchoProvider(), [
            ("empty", "", "  "), ("valid", "hola", "hola")])
        self.assertFalse(results[0].success)
        self.assertIn("invalid_segment", results[0].error)
        self.assertEqual(requests[1].context_segments, ())
        self.assertTrue(results[1].success)

    async def test_bounded_queue_reports_overflow_in_sequence(self):
        gate = asyncio.Event()

        class GatedProvider(TranslatorProvider):
            name = "gated"

            async def translate(self, request):
                await gate.wait()
                return f"EN:{request.normalized_text}"

        results = []

        async def collect(result, snapshot):
            results.append(result)

        config = TranslationConfig(enabled=True, provider="test", queue_maxsize=1)
        engine = TranslationEngine(config, GatedProvider(), "session-a", collect)
        await engine.start()
        await engine.submit("1", "one", "one")
        await asyncio.sleep(0)
        await engine.submit("2", "two", "two")
        await engine.submit("3", "three", "three")
        gate.set()
        await engine.wait_idle()
        await engine.close()
        self.assertEqual([result.sequence for result in results], [1, 2, 3])
        self.assertEqual(results[2].error, "translation_queue_full")
        self.assertEqual(engine.metrics.max_queue_depth, 1)

    async def test_reset_clears_context_sequence_and_rejects_stale_result(self):
        results = []

        async def collect(result, snapshot):
            results.append(result)

        config = TranslationConfig(enabled=True, provider="test")
        engine = TranslationEngine(config, EchoProvider(), "old", collect)
        await engine.start()
        old_request = await engine.submit("old:1", "raw", "normal")
        await engine.wait_idle()
        old_result = results.pop()
        await engine.reset("new")
        new_request = await engine.submit("new:1", "nuevo", "nuevo")
        await engine.wait_idle()
        await engine._store_result(old_result, engine._generation - 1)
        await engine.close()
        self.assertEqual(new_request.sequence, 1)
        self.assertEqual(new_request.context_segments, ())
        self.assertEqual([result.session_id for result in results], ["new"])
        self.assertEqual(engine.metrics.stale_discarded, 1)

    async def test_disabled_and_missing_provider_configuration(self):
        disabled = build_translation_engine(TranslationConfig(), "s")
        await disabled.start()
        self.assertEqual(disabled.status.state, "disabled")
        self.assertIsNone(await disabled.submit("1", "raw", "normal"))
        await disabled.close()
        missing = build_translation_engine(TranslationConfig(enabled=True), "s")
        await missing.start()
        self.assertEqual(missing.status.state, "misconfigured")
        self.assertIn("TRANSLATION_PROVIDER", missing.status.message)
        await missing.close()


class DeepLProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_text_and_context_are_separate(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"translations": [{"text": "Current only."}]}).encode()

        def opener(request, timeout):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            captured["authorization"] = request.headers["Authorization"]
            return Response()

        provider = DeepLTranslatorProvider("secret", opener=opener)
        request = TranslationRequest(
            "s", "2", 2, "actual", "actual",
            (TranslationContextSegment("1", 1, "contexto anterior"),),
            "es", "en", 1.)
        self.assertEqual(await provider.translate(request), "Current only.")
        self.assertEqual(captured["body"]["text"], ["actual"])
        self.assertEqual(captured["body"]["context"], "contexto anterior")
        self.assertNotIn("contexto anterior", captured["body"]["text"])
        self.assertEqual(captured["authorization"], "DeepL-Auth-Key secret")


class TranslationReplayTests(unittest.TestCase):
    def test_medical_replay_includes_context_translation_and_metrics(self):
        fixture = Path(__file__).parents[1] / "benchmarks" / "medical_real_snapshots.json"
        output = StringIO()
        argv = ["replay_fixture.py", str(fixture), "--perf-repeats", "0"]
        with patch.object(sys, "argv", argv), redirect_stdout(output):
            asyncio.run(async_main())
        rendered = output.getvalue()
        self.assertIn("SEGMENT 01", rendered)
        self.assertIn("NORMALIZED ES:", rendered)
        self.assertIn("CONTEXT:", rendered)
        self.assertIn("ENGLISH:\n[MOCK EN]", rendered)
        self.assertIn("TRANSLATION_SUMMARY segments=16 successes=16 failures=0", rendered)
        self.assertIn("TRANSLATION_QUEUE_DELAY_MS", rendered)


if __name__ == "__main__":
    unittest.main()

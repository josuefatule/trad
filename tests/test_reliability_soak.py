import unittest
import asyncio
import json
import os
from pathlib import Path
from benchmarks.reliability_soak import simulate


class ProlongedReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_hour_virtual_load_bounds_integrity_and_cleanup(self):
        loop=asyncio.get_running_loop();debug=loop.get_debug();loop.set_debug(False)
        try:report=await simulate()
        finally:loop.set_debug(debug)
        if os.getenv("M7_SOAK_OUTPUT"):
            Path(os.environ["M7_SOAK_OUTPUT"]).write_text(json.dumps(report,indent=2),encoding="utf-8")
        self.assertGreaterEqual(report["simulated_seconds"],3600)
        self.assertTrue(report["word_integrity"])
        self.assertEqual(report["workers_after_stop"],0)
        self.assertEqual(report["tasks_before"],report["tasks_after"])
        self.assertGreater(report["journal_truncated_events"],0)
        self.assertEqual(report["stop_outcome"],"incomplete") # Injected auth failures are never hidden.

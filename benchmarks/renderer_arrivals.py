"""Synthetic English layout probes at real READY times; not translations or E2E measurements."""
import json
from pathlib import Path
from app.captions.segment_manager import SegmentManager
from replay_fixture import replay

if __name__ == "__main__":
    fixture = json.loads(Path("benchmarks/medical_real_snapshots.json").read_text(encoding="utf-8"))
    arrivals = [{"at_ms": round(now * 1000, 3),
                 "text": f"English layout probe number {index} arrives immediately."}
                for index, (now, segment) in enumerate(
                    ((now, segment) for now, result in replay(fixture["events"], SegmentManager())
                     for segment in result.ready_segments), 1)]
    print(json.dumps(arrivals))

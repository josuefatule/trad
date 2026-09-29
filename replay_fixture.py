"""Replay timed full snapshots using the exact manager and timer rules, without GPU."""
import argparse
import json
from pathlib import Path

from app.captions.segment_manager import SegmentConfig, SegmentManager
from app.captions.transcript_state import TranscriptState


def replay(events, manager):
    state = TranscriptState()
    last = 0.
    for event in events:
        now = float(event["at"])
        if now < last:
            raise ValueError("Fixture events must be ordered by receive time")
        step = last + manager.config.tick_seconds
        while step < now - 1e-9:
            result = manager.tick(step)
            if result.ready_segments or result.events:
                yield step, result
            step += manager.config.tick_seconds
        payload = event["payload"]
        if payload.get("type") == "ready_to_stop":
            yield now, manager.finish(now)
            return
        if "lines" in payload:
            state.update(payload)
            yield now, manager.update(state, now)
        else:
            yield now, manager.tick(now)
        last = now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    manager = SegmentManager(SegmentConfig.from_env(), "replay")
    previous = None
    late = 0
    for now, result in replay(fixture["events"], manager):
        if result.pending_segment != previous:
            print(f"{now:7.3f} PENDING {result.pending_segment}")
            previous = result.pending_segment
        for segment in result.ready_segments:
            print(f"{now:7.3f} READY {json.dumps(dataclass_dict(segment), ensure_ascii=False)}")
        for event in result.events:
            if event["type"] == "late_revision_detected":
                late += 1
                print(f"{now:7.3f} LATE {json.dumps(event, ensure_ascii=False)}")
    print(f"SUMMARY segments={len(manager.emitted_segments)} late_revisions={late}")


def dataclass_dict(value):
    from dataclasses import asdict
    return asdict(value)


if __name__ == "__main__":
    main()

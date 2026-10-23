"""Actual TRAD state and segmentation, driven by a simulated serial clock.

No HTTP relay, translation engine, auth substitute, or caption publication.
"""
from copy import deepcopy
from app.captions.transcript_state import TranscriptState
from app.captions.segment_manager import SegmentConfig, SegmentManager


def compact(text):
    return ' '.join(text.split())


class TradConsumer:
    def __init__(self, session_id, sink=lambda e: None):
        self.session_id, self.sink = session_id, sink
        self.state = TranscriptState()
        self.manager = SegmentManager(SegmentConfig(), session_id)
        self.now = 0.
        self.next_tick = self.manager.config.tick_seconds
        self.last_sequence = -1
        self.previous_lines = []
        self.ready = []
        self.events = []
        self.closed = False

    def _result(self, result, phase):
        self.ready.extend(result.ready_segments)
        self.events.extend(result.events)
        if result.events or result.ready_segments:
            self.sink({'phase': phase, 'simulated_serial_s': self.now,
                       'segmentation': result.to_dict()})
        # Ordered text conservation, including literal signs/units/punctuation.
        reconstructed = ' '.join([*(s.text for s in self.ready), result.pending_segment])
        if compact(reconstructed) != compact(self.state.confirmed_text):
            raise RuntimeError('New text loss/duplication between confirmed and READY/pending')
        if any(e['type'] == 'late_revision_detected' for e in result.events):
            raise RuntimeError('Unexpected revision of immutable confirmed source')

    def receive(self, payload, now):
        if self.closed:
            raise RuntimeError('Consumer already stopped')
        if payload['session_id'] != self.session_id:
            raise ValueError('Foreign session event')
        if payload['adapter_sequence'] != self.last_sequence + 1:
            raise ValueError('ASR event sequence mismatch')
        if now < self.now:
            raise ValueError('Nonmonotonic consumer clock')
        self.last_sequence += 1
        while self.next_tick < now - 1e-8:
            self.now = self.next_tick
            self._result(self.manager.tick(self.now), 'tick')
            self.next_tick += self.manager.config.tick_seconds
        self.now = now
        if 'lines' in payload:
            if payload['lines'][:len(self.previous_lines)] != self.previous_lines:
                raise RuntimeError('Confirmed snapshot prefix changed')
            self.previous_lines = deepcopy(payload['lines'])
        self.state.update(payload)
        if payload.get('type') == 'ready_to_stop':
            if not payload.get('audio_eof'):
                raise RuntimeError('Terminal before audio EOF')
            self._result(self.manager.finish(now), 'terminal')
            self.closed = True
        elif 'lines' in payload:
            self._result(self.manager.update(self.state, now), 'snapshot')
        elif payload.get('type') == 'error':
            raise RuntimeError('Adapter failed; no complete result')

    def visual_clear(self, hub):
        """Use the existing visual contract; never reset ASR/state/segmentation."""
        return hub.clear_captions(self.session_id, hub.visual_generation)

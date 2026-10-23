"""Bounded rolling PCM and timestamped, append-only local agreement.

No decoder imports here: the callable receives only a copy of available audio.
Confirmed text goes to the event sink, not an unbounded in-memory transcript.
EOF leaves an explicitly unconfirmed tail; it does not invent a second vote.
"""
from dataclasses import dataclass, asdict
import math
import hashlib
import re
import unicodedata
import time
import numpy as np
from trad_lab.metrics import TOKEN

RATE = 16000
CONFIRM_TOKEN = re.compile(TOKEN.pattern+r'|[%+−<>≤≥/=]|(?<=\d)-|-(?=\s*\d)',re.UNICODE)


@dataclass(frozen=True)
class Word:
    text: str
    start: float
    end: float
    probability: float = 1.0

    @property
    def key(self):
        text=unicodedata.normalize('NFKC',self.text).casefold().replace('’',"'").replace('‘',"'").replace('−','-')
        if text.strip()=='-':return ('-',)
        return tuple(CONFIRM_TOKEN.findall(text))


@dataclass(frozen=True)
class Config:
    window_s: float = 15
    update_s: float = 2
    minimum_age_s: float = 1
    agreement: int = 2
    timestamp_tolerance_s: float = .8
    max_words: int = 512
    mode: str = 'fixed'
    max_buffer_s: float = 30

    def __post_init__(self):
        if not (0 < self.update_s < self.window_s <= 30):
            raise ValueError('Expected 0 < update < window <= 30 seconds')
        if (self.agreement not in (2, 3) or not 0 <= self.minimum_age_s < self.window_s
                or not math.isfinite(self.timestamp_tolerance_s) or self.timestamp_tolerance_s <= 0
                or self.max_words <= 0):
            raise ValueError('Unsupported confirmation policy')
        if self.mode not in ('fixed','adaptive') or not self.window_s <= self.max_buffer_s <= 30:
            raise ValueError('Invalid bounded buffer policy')


class HorizonError(RuntimeError):
    """Unconfirmed speech would leave the bounded window; never hide this loss."""


def same_occurrence(a, b, tolerance):
    """Exact words must also overlap in time; fast repetitions are distinct."""
    overlap = min(a.end,b.end)-max(a.start,b.start)
    return (a.key == b.key and abs(a.end-b.end) <= tolerance and
            (overlap > 0 or abs((a.start+a.end)-(b.start+b.end)) <= .12))


def join_continuations(words):
    """Keep the decoder's exact text, but never commit half a whitespace word.

    Faster-Whisper can expose ' norma', '-tensive' as separate word records.
    Joining literal continuations is token assembly, not a medical correction.
    """
    result=[]
    for w in words:
        if result and w.text and not w.text[0].isspace() and not result[-1].text.endswith((' ','\n')):
            previous=result.pop()
            result.append(Word(previous.text+w.text,previous.start,max(previous.end,w.end),min(previous.probability,w.probability)))
        else:result.append(w)
    return result


class Incremental:
    def __init__(self, decode, sink, config=Config()):
        self.decode, self.sink, self.config = decode, sink, config
        self.audio = np.empty(0, dtype=np.float32)
        self.received = self.decoded = 0
        self.pending = []
        self.history = []
        self.recent = []
        self.frontier = 0.
        self.closed = False
        self.serial_completion = 0.
        self.peak_samples = self.peak_words = 0
        self.calls = self.committed_count = self.revisions = 0
        self.compute_s = 0.
        self.trim_points=[]
        self.last_trim=None

    def push(self, block):
        if self.closed:
            raise RuntimeError('Audio after EOF')
        block = np.asarray(block)
        if block.ndim != 1 or block.dtype != np.float32 or not np.isfinite(block).all():
            raise ValueError('Finite mono float32 PCM required')
        step = round(self.config.update_s * RATE)
        if len(block) > step:
            raise ValueError('Feed at most one update per call; preserve availability')
        self.received += len(block)
        self.audio = np.concatenate((self.audio, block))
        try:self._trim()
        except Exception:
            self.closed=True
            raise
        self.peak_samples = max(self.peak_samples, len(self.audio))
        if self.received - self.decoded >= step:
            try:self._update()
            except Exception:
                self.closed=True
                raise

    def _trim(self):
        self.last_trim=None
        if self.config.mode=='fixed':
            self.audio=self.audio[-round(self.config.window_s*RATE):]
            return
        available=self.received/RATE
        start=(self.received-len(self.audio))/RATE
        desired=available-self.config.window_s
        points=[t-.4 for t in self.trim_points if start < t-.4 <= desired]
        cut=max(points) if points else start
        reason='confirmed_sentence'
        minimum=available-self.config.max_buffer_s
        if cut < minimum:
            # The hard cap can use a confirmed word boundary; never throw away
            # unconfirmed speech just to keep producing an apparently valid run.
            words=[w.end-.4 for w in self.recent if w.end-.4 >= minimum and w.end <= self.frontier]
            if words:
                cut=min(words);reason='confirmed_word_at_hard_cap'
            else:
                # At startup or a long pause there may be no confirmed words.
                # Keep every currently provisional word plus left context;
                # trimming text-free older context is not proof of acoustic
                # silence (VAD/ASR false negatives remain an evaluation risk).
                protected=self.pending[0].start-.4 if self.pending else available
                cut=min(desired,protected)
                if cut < minimum:raise HorizonError('No confirmed boundary within bounded adaptive buffer')
                reason='before_provisional_or_empty_hypothesis'
        if cut>start:
            offset=round((cut-start)*RATE)
            self.audio=self.audio[offset:]
            self.last_trim={'at_s':available,'from_s':start,'to_s':start+offset/RATE,'reason':reason}
        if len(self.audio)>round(self.config.max_buffer_s*RATE)+1:
            raise HorizonError('Adaptive audio bound exceeded')

    def _update(self):
        if self.received == self.decoded:
            return
        available = self.received / RATE
        start = (self.received - len(self.audio)) / RATE
        if self.pending and self.pending[0].start < start - .1:
            raise HorizonError('Unconfirmed prefix fell outside window')
        before = time.perf_counter()
        decoder_words = self.decode(self.audio.copy(), start)
        elapsed = time.perf_counter() - before
        if len(decoder_words) > self.config.max_words:
            raise RuntimeError('Hypothesis word bound exceeded')
        for w in decoder_words:
            if not all(math.isfinite(x) for x in (w.start, w.end, w.probability)) or not (start - .05 <= w.start <= w.end <= available + .05):
                raise ValueError('Decoder word outside available audio')
        words=join_continuations(decoder_words)
        # Time gates distinguish repeated words. Exact suffix anchoring handles
        # small timestamp shifts across overlapping windows without fuzzy text.
        # With no lexical anchor, a word straddling the immutable time frontier
        # is ambiguous. Do not append its suffix as a new occurrence (e.g. a
        # later 'high attention' re-decode of already committed 'hypertension').
        boundary_conflicts = [asdict(w) for w in words if w.key and
                              w.start < self.frontier-.05 and w.end > self.frontier+.02]
        candidate = [w for w in words if w.key and w.start >= self.frontier-.05]
        anchor = 0
        for n in range(min(8, len(self.recent), len(words)), 0, -1):
            tail = self.recent[-n:]
            matches = []
            for i in range(len(words) - n + 1):
                chunk = words[i:i+n]
                if all(same_occurrence(a,b,self.config.timestamp_tolerance_s) for a,b in zip(tail, chunk)):
                    matches.append((sum(abs(a.end-b.end) for a,b in zip(tail,chunk)), i+n))
            if matches:
                _, anchor = min(matches)
                candidate = [w for w in words[anchor:] if w.key]
                break
        if self.pending and candidate:
            self.revisions += int([w.key for w in candidate[:len(self.pending)]] != [w.key for w in self.pending])
        votes = self.history[-(self.config.agreement - 1):]
        stable = 0
        if len(votes) == self.config.agreement - 1:
            for i, w in enumerate(candidate):
                if w.end > available - self.config.minimum_age_s:
                    break
                if not all(i < len(v) and same_occurrence(v[i],w,self.config.timestamp_tolerance_s) for v in votes):
                    break
                stable += 1
        confirmed = candidate[:stable]
        self.compute_s += elapsed
        self.serial_completion = max(available, self.serial_completion) + elapsed
        self.calls += 1
        event = {'type':'update','call':self.calls,'received_samples':self.received,
                 'window_start_sample':self.received-len(self.audio),'window_end_sample':self.received,
                 'window_f32_sha256':hashlib.sha256(self.audio.astype('<f4').tobytes()).hexdigest(),
                 'available_s':available,'inference_s':elapsed,'serial_completion_s':self.serial_completion,
                 'anchor_index':anchor,'hypothesis':[asdict(w) for w in words],
                 'decoder_words':[asdict(w) for w in decoder_words],
                 'boundary_conflicts':boundary_conflicts if not anchor else [],
                 'trim':self.last_trim,
                 'provisional':[asdict(w) for w in candidate[stable:]],
                 'confirmed':[asdict(w) for w in confirmed]}
        self.sink(event)
        if confirmed:
            self.frontier = confirmed[-1].end
            self.recent = (self.recent + confirmed)[-32:]
            self.committed_count += len(confirmed)
            self.trim_points=(self.trim_points+[w.end for w in confirmed if w.text.rstrip().endswith(('.','?','!'))])[-128:]
        self.pending = candidate[stable:]
        self.history = [v[stable:] for v in votes] + [self.pending]
        self.history = self.history[-(self.config.agreement - 1):]
        self.peak_words = max(self.peak_words, len(words), len(self.recent), sum(len(v) for v in self.history))
        self.decoded = self.received

    def finish(self):
        if self.closed:
            raise RuntimeError('Duplicate EOF')
        try:self._update()
        except Exception:
            self.closed=True
            raise
        self.closed = True
        self.sink({'type':'eof','available_s':self.received/RATE,
                   'unconfirmed_tail':[asdict(w) for w in self.pending],
                   'scope':'No future silence, duplicate vote, or forced stable commit'})
        return {'calls':self.calls,'compute_s':self.compute_s,'committed_words':self.committed_count,
                'unconfirmed_tail_words':len(self.pending),'provisional_revision_updates':self.revisions,
                'peak_audio_samples':self.peak_samples,'peak_word_state':self.peak_words}

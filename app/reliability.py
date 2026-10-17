"""Measured operational health, bounded UI journal and metadata-only incidents."""
import asyncio
from collections import Counter, deque
from copy import deepcopy
from dataclasses import asdict, dataclass
import json
import logging
import math
import os
import random
import time
from array import array
from datetime import datetime, timezone

logger = logging.getLogger("captions")


@dataclass(frozen=True)
class ReliabilityConfig:
    connect_attempts: int = 3
    backoff_seconds: float = .5
    backoff_max_seconds: float = 4.
    owner_timeout_seconds: float = 15.
    audio_stale_seconds: float = 5.
    audio_signal_rms: float = .015
    asr_stale_seconds: float = 15.
    max_session_seconds: float = 7200.
    max_asr_characters: int = 300000
    max_ready_segments: int = 12000
    max_ready_characters: int = 600000
    max_asr_sources: int = 6000
    max_asr_events: int = 100000
    websocket_max_bytes: int = 8000000
    websocket_send_seconds: float = 3.
    journal_events: int = 512
    journal_max_bytes: int = 2000000
    ui_history_segments: int = 500
    ui_transcript_characters: int = 60000
    control_flush_seconds: float = 5.

    def __post_init__(self):
        for key,value in asdict(self).items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Invalid reliability setting: {key}")
        if self.connect_attempts > 10 or self.journal_events > 10000 or self.max_session_seconds > 86400:
            raise ValueError("Reliability limit exceeds supported operational budget")

    @classmethod
    def from_env(cls):
        return cls(**{name:type(value)(os.getenv("RELIABILITY_"+name.upper(),value))
                      for name,value in asdict(cls()).items()})


def backoff(attempt, base, maximum, random_value=None):
    random_value = random.random() if random_value is None else random_value
    return min(maximum, base * 2 ** min(attempt, 20)) * (.75 + .25 * random_value)


def incident(component, event, session_id=None, severity="INFO", **metadata):
    # Callers pass identifiers/counts/codes, never content/credentials.
    logger.log(getattr(logging,severity),json.dumps({"timestamp":datetime.now(timezone.utc).isoformat(),"component":component,"event":event,
               "session_id":session_id,"severity":severity,**metadata},ensure_ascii=False))


class OperationalRun:
    def __init__(self, config=None, clock=time.monotonic):
        self.config=config or ReliabilityConfig()
        self.clock=clock
        self.session_id=None
        self.reset(None)

    def reset(self, session_id):
        self.session_id=session_id;self.started=self.clock();self.ended=None
        self.last_audio=None;self.last_asr=None;self.last_translation=None
        self.last_signal=None;self.audio_rms=0.
        self.retained_asr_characters=0;self.source_count=0
        self.ready_characters=0
        self.audio_frames=0;self.audio_bytes=0;self.asr_messages=0;self.ready_count=0
        self.pending_characters=0;self.asr_characters=0;self.latest_transcript=None
        self.latest_pending=""
        self.latest_config=None;self.last_translation_sequence=0
        self.stop_requested_at=None;self.audio_eof=False;self.asr_final=False
        self.stop_reason=None
        self.outcome="not_started";self.failure_reason=None;self.state="DISCONNECTED"
        self.failure_details=None
        self.state_since=self.clock();self.state_reason="no_session"
        self.journal=deque(maxlen=self.config.journal_events);self.cursor=0;self.truncated_events=0
        self.journal_bytes=0
        self.counters=Counter();self.capture_sender=None;self.translator=None
        self.watchdog_stop_sent=False
        self.owner_age_getter=lambda:None
        self.wlk_connected_at=None;self.wlk_disconnected_at=None

    def transition(self, state, reason):
        if (self.state,self.state_reason)==(state,reason):return
        previous=self.state;duration=self.clock()-self.state_since
        self.state=state;self.state_reason=reason;self.state_since=self.clock()
        incident("session","health_changed",self.session_id,old_state=previous,new_state=state,
                 reason=reason,duration_seconds=round(duration,3))

    def audio(self, data):
        if data:
            self.last_audio=self.clock();self.audio_frames+=1;self.audio_bytes+=len(data)
            samples=array('h');samples.frombytes(data[:len(data)//2*2])
            self.audio_rms=math.sqrt(sum(value*value for value in samples)/len(samples))/32768 if samples else 0.
            if self.audio_rms>=self.config.audio_signal_rms:self.last_signal=self.clock()
        else:
            self.audio_eof=True
            if self.stop_requested_at is None:self.stop_requested_at=self.clock()

    def asr(self, payload):
        self.last_asr=self.clock();self.asr_messages+=1
        if payload.get("type")=="ready_to_stop":self.asr_final=True

    def retain(self, message):
        kind=message.get("type")
        if kind=="config":self.latest_config=deepcopy(message)
        if kind=="asr":
            transcript=message.get("transcript",{})
            self.latest_transcript={key:transcript.get(key,"") for key in ("partial_text","confirmed_text")}
            text=self.latest_transcript["confirmed_text"]
            self.asr_characters=len(text)
            self.latest_transcript["confirmed_text"]=text[-self.config.ui_transcript_characters:]
            self.latest_transcript["history_truncated_characters"]=max(0,len(text)-self.config.ui_transcript_characters)
            partial=self.latest_transcript["partial_text"]
            self.latest_transcript["partial_text"]=partial[-self.config.ui_transcript_characters:]
            self.latest_transcript["partial_truncated_characters"]=max(0,len(partial)-self.config.ui_transcript_characters)
        segmentation=message.get("segmentation")
        if segmentation is not None:
            self.pending_characters=len(segmentation.get("pending_segment",""))
            self.latest_pending=segmentation.get("pending_segment","")[-self.config.ui_transcript_characters:]
            self.ready_count+=len(segmentation.get("ready_segments",[]))
            self.ready_characters+=sum(len(segment["text"]) for segment in segmentation.get("ready_segments",[]))
            if segmentation.get("ready_segments"):
                self.append({"type":"segmentation","protocol_version":1,"session_id":self.session_id,
                    "segmentation":{"pending_segment":segmentation.get("pending_segment",""),
                                    "ready_segments":segmentation["ready_segments"],"events":[]},
                    "normalization":message.get("normalization")})
        if kind=="translation":
            self.last_translation=self.clock()
            self.last_translation_sequence=message["translation"]["sequence"]
            if not message["translation"]["success"]:self.counters["translation_failures"]+=1
            self.append(message)
        if kind=="status" and message.get("state")=="stopped":
            self.ended=self.clock()
            self.outcome="incomplete" if message.get("completion")=="incomplete" or self.counters["translation_failures"] or self.failure_reason else "complete"
            self.transition("DEGRADED" if self.outcome=="incomplete" else "READY", "stop_"+self.outcome)

    def append(self, message):
        self.cursor+=1
        size=len(json.dumps(message,ensure_ascii=False).encode("utf-8"))
        if size>self.config.journal_max_bytes:
            self.truncated_events+=1
            incident("operator","journal_oversize_not_retained",self.session_id,"WARNING",journal_id=self.cursor,bytes=size)
            return
        while self.journal and (len(self.journal)==self.journal.maxlen or self.journal_bytes+size>self.config.journal_max_bytes):
            self.journal_bytes-=self.journal.popleft()["retained_bytes"];self.truncated_events+=1
        self.journal.append({"journal_id":self.cursor,"message":deepcopy(message),"retained_bytes":size})
        self.journal_bytes+=size

    def journal_snapshot(self, after=0):
        first=self.journal[0]["journal_id"] if self.journal else self.cursor+1
        translations=[e["message"]["translation"]["sequence"] for e in self.journal
                      if e["message"]["type"]=="translation"]
        retained=[entry for entry in self.journal if entry["journal_id"]>after]
        gap=(after>self.cursor or after<first-1 or
             any(entry["journal_id"]!=after+index+1 for index,entry in enumerate(retained)) or
             (retained[-1]["journal_id"] if retained else after)<self.cursor)
        return {"cursor":self.cursor,"history_gap":gap,"truncated_events":self.truncated_events,
                "first_translation_sequence":min(translations) if translations else self.last_translation_sequence+1,
                "events":list(self.journal) if gap else retained,
                "transcript":self.latest_transcript,"config":self.latest_config,"pending_segment":self.latest_pending,
                "ui_history_segments":self.config.ui_history_segments}

    def fail(self, reason):
        if self.outcome=="incomplete" and self.failure_reason==reason and self.failure_details is not None:return
        self.ended=self.clock();self.outcome="incomplete";self.failure_reason=reason
        self.wlk_disconnected_at=self.clock()
        self.transition("ERROR",reason)
        self.failure_details={"pending_characters":self.pending_characters,"asr_final":self.asr_final,
            "translation_pending":self.translator.pending_count if self.translator else 0,
            "last_result_sequence":self.last_translation_sequence,"ready_segments":self.ready_count}
        incident("session","incomplete",self.session_id,"ERROR",reason=reason,
                 **self.failure_details)

    async def request_stop(self, reason="operator_stop"):
        if self.stop_requested_at is not None:return False
        self.stop_requested_at=self.clock()
        self.stop_reason=reason
        incident("session","stop_requested",self.session_id,reason=reason)
        if self.capture_sender:
            await asyncio.wait_for(self.capture_sender({"type":"operator_command","command":"stop",
                                  "protocol_version":1,"session_id":self.session_id}),2.)
        return True

    def health(self, hub, owner_age=None):
        now=self.clock();active=hub.state in {"connecting","live","draining"}
        age=lambda value:None if value is None else round(max(0,now-value),3)
        audio_age=age(self.last_audio);asr_age=age(self.last_asr)
        reasons=[]
        if hub.state=="live" and not self.audio_eof:
            if (audio_age if audio_age is not None else now-self.started)>self.config.audio_stale_seconds:
                reasons.append("audio_frames_missing")
            if (self.last_signal is not None and now-self.last_signal<self.config.asr_stale_seconds and
                    (asr_age if asr_age is not None else now-self.started)>self.config.asr_stale_seconds):
                reasons.append("asr_messages_missing")
        if active and owner_age is not None and owner_age>self.config.owner_timeout_seconds:reasons.append("operator_owner_missing")
        if active and len(hub.subscribers)==0:reasons.append("overlay_no_subscribers")
        translator=self.translator.snapshot() if self.translator else None
        if translator and translator.get("health") in {"DEGRADED","ERROR","RECOVERING"}:reasons.append("translator_"+translator["health"].lower())
        if active and hub.state=="connecting":pass
        elif active and reasons:self.transition("DEGRADED",",".join(reasons))
        elif hub.state=="live":self.transition("READY" if self.audio_frames and self.asr_messages else "RECOVERING",
                                              "audio_and_asr_observed" if self.audio_frames and self.asr_messages else "awaiting_flow")
        components={"fastapi":{"state":"READY","last_seen_mono":now},
            "wlk":{"state":"DISCONNECTED" if self.wlk_disconnected_at or not active else "RECOVERING" if hub.state=="connecting" else "READY",
                   "last_seen_mono":self.last_asr,"connected_at_mono":self.wlk_connected_at,"disconnected_at_mono":self.wlk_disconnected_at,
                   "disconnected_duration_seconds":age(self.wlk_disconnected_at)},
            "audio":{"state":"DISCONNECTED" if not active or self.audio_eof else "DEGRADED" if "audio_frames_missing" in reasons else "READY" if self.audio_frames else "RECOVERING","last_seen_mono":self.last_audio},
            "asr":{"state":"DEGRADED" if "asr_messages_missing" in reasons else "READY" if self.asr_messages else "RECOVERING","last_seen_mono":self.last_asr,
                   "silence_or_unverified":self.last_signal is None or now-self.last_signal>=self.config.asr_stale_seconds},
            "translator":translator,"caption_hub":{"state":"READY","sequence":hub.sequence,"subscribers":len(hub.subscribers)},
            "operator":{"state":"DEGRADED" if "operator_owner_missing" in reasons else "READY" if owner_age is not None else "DISCONNECTED","age_seconds":owner_age}}
        return {"state":self.state,"reason":self.state_reason,"state_since_mono":self.state_since,
            "state_duration_seconds":round(now-self.state_since,3),"components":components,
            "duration_seconds":round((self.ended or now)-self.started,3) if self.session_id else 0,
            "audio_last_seen_mono":self.last_audio,"audio_age_seconds":audio_age,"audio_frames":self.audio_frames,"audio_bytes":self.audio_bytes,
            "asr_last_seen_mono":self.last_asr,"asr_age_seconds":asr_age,"asr_messages":self.asr_messages,
            "audio_rms":round(self.audio_rms,5),"signal_last_seen_mono":self.last_signal,
            "outcome":self.outcome,"pending_characters":self.pending_characters,"asr_final":self.asr_final,
            "stop_reason":self.stop_reason,"asr_retained_characters":self.retained_asr_characters,"asr_source_count":self.source_count,
            "ready_characters":self.ready_characters,"journal_retained_bytes":self.journal_bytes,
            "failure_details":self.failure_details,
            "owner_age_seconds":owner_age,"counters":dict(self.counters),"translator":translator,
            "journal_retained":len(self.journal),"journal_truncated":self.truncated_events}


class SafeLogFilter(logging.Filter):
    """No transcript text or arbitrary exception strings in default logs."""
    def __init__(self, secrets_supplier=lambda:(), allow_text=False):
        super().__init__();self.secrets_supplier=secrets_supplier;self.allow_text=allow_text

    def filter(self, record):
        message=record.getMessage()
        if not self.allow_text and "{" in message:
            start=message.find("{")
            try:
                payload=json.loads(message[start:])
                def safe(value):
                    if isinstance(value,dict):
                        return {key+"_characters" if key in {"text","old_text","new_text"} else key:
                                len(str(item)) if key in {"text","old_text","new_text"} else safe(item)
                                for key,item in value.items()}
                    if isinstance(value,list):return [safe(item) for item in value]
                    return value
                message=message[:start]+json.dumps(safe(payload),ensure_ascii=False)
            except ValueError:pass
        if " error=" in message:message=message.split(" error=",1)[0]+" error=see_error_category"
        for secret in self.secrets_supplier():
            if secret:message=message.replace(secret,"[REDACTED]")
        if "Authorization" in message:message="authorization_details_redacted"
        if record.exc_info:
            message+=" exception_type="+record.exc_info[0].__name__;record.exc_info=None;record.exc_text=None
        record.msg=message;record.args=()
        return True

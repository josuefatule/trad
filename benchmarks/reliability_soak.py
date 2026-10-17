"""Accelerated 60-minute operational load, virtual timing, NO external services.

Run: python -m benchmarks.reliability_soak --output benchmarks/m7_soak_results.json
Captures Python allocations, not RSS/GPU/network or a physical conference.
"""
import argparse
import asyncio
from collections import Counter
from dataclasses import asdict
import json
import logging
import random
from pathlib import Path
import threading
import time
import tracemalloc
from urllib.error import HTTPError

from app.captions.segment_manager import SegmentConfig, SegmentManager
from app.captions.transcript_state import TranscriptState
from app.captions.terminology_normalizer import TerminologyNormalizer
from app.overlay.config import CaptionConfig
from app.overlay.hub import CaptionHub
from app.reliability import OperationalRun
from app.translation import TranslationConfig, TranslationEngine


async def simulate(minutes=60):
    if minutes<60:raise ValueError("M7 duration must be at least 60 simulated minutes")
    class Clock:
        now=0.
        def __call__(self):return self.now
        async def sleep(self,seconds):self.now+=seconds;await asyncio.sleep(0)
    clock=Clock();started=time.perf_counter();tracemalloc.start()
    before_tasks=len(asyncio.all_tasks());before_threads=threading.active_count()
    run=OperationalRun(clock=clock);run.reset("soak");run.outcome="in_progress"
    hub=CaptionHub(CaptionConfig(),clock=clock,monotonic_clock=clock)
    hub.begin("soak");hub.set_state("soak","live")
    observers=[hub.subscribe() for _ in range(3)];slow=None
    manager=SegmentManager(SegmentConfig(),"soak");state=TranscriptState()
    normalizer=TerminologyNormalizer.from_config(None)
    attempts=Counter();calls=0;successes=0;failures=0;rearmed=False
    class Provider:
        name="simulation-only"
        async def translate(self,request):
            nonlocal calls
            calls+=1;attempts[request.sequence]+=1
            if request.sequence==100:raise HTTPError("https://simulation.invalid",403,"",{},None)
            if request.sequence%37==0 and attempts[request.sequence]==1:raise OSError("simulated network loss")
            return "SIMULATED EN: "+request.normalized_text
    async def result_ready(result,snapshot):
        nonlocal successes,failures
        successes+=result.success;failures+=not result.success
        hub.record_translation_status("soak",snapshot);hub.publish(result)
        run.retain({"type":"translation","session_id":"soak","translation":result.to_dict()})
    engine=TranslationEngine(TranslationConfig(enabled=True,provider="simulation"),Provider(),"soak",result_ready,
                             monotonic_clock=clock,sleep=clock.sleep,jitter=random.Random(7).random)
    await engine.start();run.translator=engine
    lines=[];source_words=[];ready_words=[];flush=Counter();health=Counter();measurements=[]
    journal_high=0;journal_bytes_high=0;subscriber_queue_high=0;caption_high=0;manager_sources_high=0;ready_count=0
    signal=b"\x00\x08"*1600;silence=b"\x00\x00"*1600
    async def accept(segmentation):
        nonlocal ready_count,rearmed
        if not segmentation.ready_segments:
            run.pending_characters=len(segmentation.pending_segment);run.latest_pending=segmentation.pending_segment
            return
        pairs=[]
        for segment in segmentation.ready_segments:
            ready_count+=1;ready_words.extend(segment.text.split());flush[segment.reason]+=1
            pairs.append((segment,normalizer.normalize(segment.id,segment.text)))
        run.retain({"type":"segmentation","segmentation":segmentation.to_dict(),
                    "normalization":{"segments":[n.to_dict() for _,n in pairs]}})
        for segment,normalized in pairs:
            if ready_count>=110 and not rearmed:engine.rearm();rearmed=True
            await engine.submit(segment.id,segment.text,normalized.normalized_text)
        await engine.wait_idle()
    last_snapshot=-1;lost_at=None
    for tick in range(minutes*600):
        clock.now+=.1
        second=tick//10;phase=second%60;speaking=phase<40
        run.audio(signal if speaking else silence)
        if tick%40==0 and second!=last_snapshot:
            last_snapshot=second
            if speaking and tick%80==0:
                text="La presión arterial requiere evaluación clínica y seguimiento regular. El paciente necesita mantener sus controles y su tratamiento."
                source_words.extend(text.split())
                lines.append({"speaker":1,"text":text,"start":str(second),"end":str(second+3.8)})
            payload={"lines":lines,"buffer_transcription":"","status":"active_transcription" if speaking else "no_audio_detected"}
            run.asr(payload);state.update(payload)
            segmentation=manager.update(state,now=clock.now)
            run.retain({"type":"asr","transcript":state.to_dict()})
            await accept(segmentation)
        else:await accept(manager.tick(now=clock.now))
        # Three normal readers, one deliberately slow reader, disconnect/CLEAR/rejoin.
        if tick==6000:slow=hub.subscribe()
        if tick==12000:
            for observer in observers:hub.unsubscribe(observer)
            observers=[]
        if tick in (6000,12050,24000):hub.clear_captions("soak",hub.visual_generation)
        if tick==12200:
            observers=[hub.subscribe() for _ in range(3)]
            for observer in observers:
                snapshot=observer.queue.get_nowait()
                assert all(c["sequence"]>snapshot["cleared_through_sequence"] for c in snapshot["captions"])
        if 24000<=tick<24200:
            if lost_at is None:lost_at=clock.now
            owner_age=clock.now-lost_at
        else:owner_age=0
        if tick%10==0:health[run.health(hub,owner_age)["state"]]+=1
        for observer in observers:
            subscriber_queue_high=max(subscriber_queue_high,observer.queue.qsize())
            while not observer.queue.empty():observer.queue.get_nowait()
        journal_high=max(journal_high,len(run.journal));caption_high=max(caption_high,len(hub.caption_history))
        journal_bytes_high=max(journal_bytes_high,run.journal_bytes)
        manager_sources_high=max(manager_sources_high,len(manager._sources))
        if tick%9000==8999:
            current,peak=tracemalloc.get_traced_memory()
            measurements.append({"simulated_seconds":round(clock.now,3),"python_traced_bytes":current,"peak_bytes":peak,
                                 "journal_retained":len(run.journal),"asr_characters":run.asr_characters})
        assert engine.pending_count<=engine.config.max_pending_results
        assert run.asr_characters<run.config.max_asr_characters
        assert len(run.journal)<=run.config.journal_events
        assert run.journal_bytes<=run.config.journal_max_bytes
    run.audio(b"");run.asr({"type":"ready_to_stop"});hub.set_state("soak","draining")
    await accept(manager.finish(now=clock.now));await engine.wait_idle()
    hub.set_state("soak","stopped");run.retain({"type":"status","state":"stopped"})
    engine_snapshot=engine.snapshot();await engine.close()
    for observer in tuple(hub.subscribers):hub.unsubscribe(observer)
    await asyncio.sleep(0)
    current,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    assert source_words==ready_words,"Loss/duplication/reordering in segmentation"
    assert not engine._workers and engine.queue_depth==0 and engine.pending_count==0
    assert slow.closed.is_set() and hub.broadcast_errors>=1
    assert len(asyncio.all_tasks())==before_tasks
    return {"kind":"virtual-clock simulation; NOT a real conference", "simulated_seconds":round(clock.now,3),
        "wall_seconds":round(time.perf_counter()-started,3),"segment_configuration":asdict(SegmentConfig()),
        "audio_frames":run.audio_frames,"audio_bytes":run.audio_bytes,"asr_messages":run.asr_messages,
        "source_lines":len(lines),"ready_segments":ready_count,"words_expected":len(source_words),"words_ready":len(ready_words),
        "word_integrity":source_words==ready_words,"flush_reasons":dict(flush),"provider_calls_simulated":calls,
        "translation_successes":successes,"translation_failures":failures,"translator":engine_snapshot,
        "stop_outcome":run.outcome,"health_sample_counts":dict(health),"journal_high_water":journal_high,
        "journal_bytes_high_water":journal_bytes_high,
        "journal_truncated_events":run.truncated_events,"caption_history_high_water":caption_high,
        "subscriber_queue_high_water":subscriber_queue_high,"slow_subscriber_evictions":hub.broadcast_errors,
        "manager_sources_high_water":manager_sources_high,"python_traced_final_bytes":current,"python_traced_peak_bytes":peak,
        "allocation_checkpoints":measurements,"tasks_before":before_tasks,"tasks_after":len(asyncio.all_tasks()),
        "threads_before":before_threads,"threads_after":threading.active_count(),"workers_after_stop":len(engine._workers),
        "queue_after_stop":engine.queue_depth,"subscribers_after_stop":len(hub.subscribers)}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",default="benchmarks/m7_soak_results.json")
    args=parser.parse_args();logging.getLogger("captions").addHandler(logging.NullHandler())
    result=asyncio.run(simulate());Path(args.output).write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result,indent=2))

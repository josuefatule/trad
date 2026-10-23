"""Bounded GPU telemetry and stop-on-OOM for this experimental WLK only."""
import json
import logging
from pathlib import Path
import threading
import time


class StopOnOOM(logging.Handler):
    def __init__(self,root):super().__init__(logging.ERROR);self.root=Path(root)
    def emit(self,record):
        message=record.getMessage().lower()
        if ('out of memory' in message or 'cuda_error_out_of_memory' in message or
                (record.exc_info and 'out of memory' in str(record.exc_info[1]).lower())):
            # No traceback/text/auth retained. Exit only this lab process;
            # coroutine finally blocks drain its evidence writers.
            (self.root/'CUDA_OOM.json').write_text(json.dumps({'status':'blocked','reason':'CUDA OOM',
                'py_ns':time.perf_counter_ns(),'policy':'stop this attempt; no retries/profile changes'}),encoding='utf-8')
            raise SystemExit(90)


class Telemetry:
    def __init__(self,root):
        self.root=Path(root);self.done=threading.Event();self.thread=None
    def start(self):
        logging.getLogger().addHandler(StopOnOOM(self.root))
        self.thread=threading.Thread(target=self.poll,daemon=True);self.thread.start()
    def poll(self):
        from trad_lab.safety import gpu_snapshot
        with (self.root/'wlk_gpu.jsonl').open('x',encoding='utf-8') as f:
            for _ in range(600):
                if self.done.is_set():break
                try:f.write(json.dumps({'py_ns':time.perf_counter_ns(),**gpu_snapshot()})+'\n');f.flush()
                except Exception:f.write(json.dumps({'error':'GPU telemetry unavailable'})+'\n');break
                self.done.wait(2)
    def close(self):
        self.done.set()
        if self.thread:self.thread.join(timeout=10)

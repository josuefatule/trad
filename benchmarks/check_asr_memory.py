"""Real loopback ASR load check with existing lab audio; no microphone or DeepL."""
import argparse
import hashlib
import json
from pathlib import Path
import threading
import time
import wave

from websockets.sync.client import connect


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--seconds',type=int,default=180)
    parser.add_argument('--language',choices=['en','es'],default='en')
    parser.add_argument('--output',default='benchmarks/asr_memory_v1/load-test.json')
    args=parser.parse_args()
    if not 30<=args.seconds<=900:raise ValueError('Load duration out of range')
    source=Path('logs/trad_lab/20261020T074247Z/streaming_plan/cardio_01.first60s.16k.wav')
    with wave.open(str(source)) as audio:
        assert (audio.getframerate(),audio.getnchannels(),audio.getsampwidth())==(16000,1,2)
        pcm=audio.readframes(audio.getnframes())
    report={'profile':'bounded','source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'source_language':'en','recognizer_language':args.language,'audio_seconds':args.seconds,
        'microphone_used':False,'translation_requested':False,'frames_sent':0,'messages_received':0,
        'max_transcript_characters':0,'final_received':False,'error':None}
    done=threading.Event()
    started=time.monotonic()
    try:
        with connect(f'ws://127.0.0.1:8000/asr?language={args.language}&mode=full',
                     proxy=None,open_timeout=20,close_timeout=3,max_size=8000000) as ws:
            config=json.loads(ws.recv(timeout=20))
            assert config.get('type')=='config' and config.get('session_language')==args.language
            assert config.get('session_language_isolation')==1
            def reader():
                try:
                    while True:
                        payload=json.loads(ws.recv(timeout=args.seconds+90))
                        report['messages_received']+=1
                        if payload.get('type')=='error' or payload.get('error'):
                            report['error']='asr_error';return
                        if payload.get('type')=='ready_to_stop':
                            report['final_received']=True;return
                        chars=sum(len(line.get('text','')) for line in payload.get('lines',[]))
                        report['max_transcript_characters']=max(report['max_transcript_characters'],chars)
                except Exception as error:
                    report['error']=type(error).__name__
                finally:done.set()
            thread=threading.Thread(target=reader,daemon=True);thread.start()
            frame_seconds=.25
            frame_bytes=8000
            for index in range(args.seconds*4):
                if done.is_set():raise RuntimeError('ASR stopped before audio EOF')
                delay=started+index*frame_seconds-time.monotonic()
                if delay>0:time.sleep(delay)
                offset=(index*frame_bytes)%len(pcm)
                ws.send(pcm[offset:offset+frame_bytes])
                report['frames_sent']+=1
                if index and index%120==0:print(f'Audio enviado: {index//4}s',flush=True)
            ws.send(b'')
            report['eof_sent']=True
            if not done.wait(60):report['error']='final_timeout'
            assert report['final_received'] and report['error'] is None,'ASR did not finish cleanly'
            assert report['max_transcript_characters']>0,'ASR returned no text'
    except Exception as error:
        if report['error'] is None:report['error']=type(error).__name__
        raise
    finally:
        report['wall_seconds']=round(time.monotonic()-started,3)
        report['result']='PASS' if report['final_received'] and not report['error'] and report['max_transcript_characters'] else 'FAIL'
        Path(args.output).write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)


if __name__=='__main__':main()

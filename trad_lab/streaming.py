"""Authenticated lab-only Chrome capture and before/after segmentation analysis.

Does NOT start/restart services. Requires independently authorized isolated
servers on 18000/18010. Uses unmodified Operator/CAPTURE, real auth/owner/EOF,
and a fake audio file through the browser's normal getUserMedia path.
"""
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import urllib.request
import wave

from .audio import decode, digest, write_wav
from .metrics import metrics
from .runner import save
from .safety import LiveGuard


def analyze_capture(records,reference=None):
    from app.captions.transcript_state import TranscriptState
    from app.captions.segment_manager import SegmentConfig,SegmentManager
    configs=[r['message'] for r in records if r['message'].get('type')=='config']
    if len(configs)!=1:raise ValueError('One authenticated session config required')
    config=configs[0];sid=config['session_id'];wlk=config.get('wlk',{})
    if config.get('direction',{}).get('source_language')!='en':raise ValueError('English session required')
    if (wlk.get('session_language_isolation')!=1 or wlk.get('session_language')!='en'
            or wlk.get('mode')!='full' or not wlk.get('useAudioWorklet')):
        raise ValueError('Required WLK language/PCM/full handshake missing')
    for cap in ('operator_console','operator_recovery','session_direction','captions_clear'):
        if config.get('capabilities',{}).get(cap)!=1:raise ValueError('Missing authorized capture capability')
    state=TranscriptState();manager=SegmentManager(SegmentConfig(),sid)
    ready={};replayed=[];late=[];snapshots=[];stopped=[]
    for record in records:
        data=record['message']
        if data.get('session_id')!=sid:continue
        if data.get('type')=='asr':
            payload=data['payload'];state.update(payload)
            result=(manager.finish(now=record['at']) if payload.get('type')=='ready_to_stop' else manager.update(state,now=record['at']))
            replayed.extend(s.text for s in result.ready_segments);late.extend(result.events)
            snapshots.append({'at':record['at'],'payload':payload,'confirmed_text':state.confirmed_text})
        for segment in (data.get('segmentation') or {}).get('ready_segments',[]):
            if segment['id'] in ready and ready[segment['id']]!=segment['text']:
                raise ValueError('READY ID revised in capture')
            ready[segment['id']]=segment['text']
        if data.get('type')=='status' and data.get('state')=='stopped':stopped.append(data)
    if not stopped:raise ValueError('Captured session did not report STOP')
    raw=state.confirmed_text;joined=' '.join(ready.values())
    return {'session_id':sid,'config':config,'transcript_status':'available' if raw.strip() else 'no_transcript',
        'raw_before_segment_manager':raw,'ready_after_segment_manager':joined,
        'raw_metrics':metrics(reference,raw) if reference is not None else None,
        'ready_metrics':metrics(reference,joined) if reference is not None else None,
        'raw_vs_ready':metrics(raw,joined),'ready_segments':len(ready),'snapshots':snapshots,
        'stop':stopped[-1],'replay_default_config':SegmentConfig().__dict__,
        'replay_ready_text':' '.join(replayed),'replay_events':late,
        'replay_caution':'RAW snapshots replayed with baseline defaults, without original tick scheduling; actual READY is authoritative',
        'interpretation':'Text differences locate stages; they do not alone establish medical correctness or audio equivalence.'}


def capture(args):
    """No service creation here: human must authorize and start isolated servers."""
    parts=urlsplit(args.url)
    if parts.scheme!='http' or parts.hostname not in {'127.0.0.1','localhost'} or parts.port!=18010:
        raise ValueError('Only isolated loopback TRAD-LAB port 18010 is allowed; never use production 8010')
    production_guard=LiveGuard()
    if not production_guard.check()['safe']:raise RuntimeError('Production TRAD is active or unknown')
    with urllib.request.urlopen(args.url+'/api/operator/bootstrap',timeout=4) as r:boot=json.load(r)
    req=urllib.request.Request(args.url+'/api/operator/status',headers={'X-Operator-Token':boot['control_token']})
    with urllib.request.urlopen(req,timeout=4) as r:status=json.load(r)
    if status.get('translator',{}).get('state')!='disabled' or not status.get('can_start'):
        raise RuntimeError('Isolated lab must have translation disabled and no active session')
    del boot
    source=Path(args.audio).resolve()
    with wave.open(str(source),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate())!=(1,2,16000):raise ValueError('Supply derived mono s16 16000-Hz WAV')
        expected_bytes=f.getnframes()*2
    reference=Path(args.reference).read_text(encoding='utf-8-sig') if args.reference else None
    out=Path(args.out).resolve()
    if out.exists():raise FileExistsError('Streaming output must be a new directory')
    out.mkdir(parents=True)
    browser=shutil.which('chrome') or next((str(p) for p in [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')] if p.exists()),None)
    if not browser:raise RuntimeError('Chrome/Edge unavailable; no install attempted')
    from websockets.sync.client import connect
    records=[];pcm=[];eof=False;capture_session=None;page_session=None;attached=[];responses={};serial=0;origin=None
    target_sessions={}
    session_sockets=set();transport_tail=[]
    with tempfile.TemporaryDirectory(prefix='trad-lab-',dir=out) as tmp:
        profile=Path(tmp)/'profile'
        process=subprocess.Popen([browser,'--headless=new','--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check',
            '--disable-background-networking','--disable-background-timer-throttling','--disable-renderer-backgrounding',
            '--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream',
            '--use-file-for-fake-audio-capture='+str(source)+'%noloop','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,'CREATE_NO_WINDOW') else 0)
        try:
            active=profile/'DevToolsActivePort';deadline=time.monotonic()+20
            while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
            lines=active.read_text().splitlines();debug_url=f'ws://127.0.0.1:{lines[0]}{lines[1]}'
            with connect(debug_url,proxy=None,open_timeout=5) as ws:
                def event(message):
                    nonlocal capture_session,origin,eof
                    if 'id' in message:responses[message['id']]=message;return
                    method=message.get('method');p=message.get('params',{});session=message.get('sessionId')
                    if method=='Target.attachedToTarget':attached.append(p)
                    if method=='Target.targetInfoChanged':
                        info=p['targetInfo']
                        if '/capture' in info.get('url',''):capture_session=target_sessions.get(info['targetId'],capture_session)
                    if method=='Network.webSocketCreated' and urlsplit(p.get('url','')).path=='/ws/session':
                        session_sockets.add((session,p['requestId']))
                    if (session,p.get('requestId')) not in session_sockets:return
                    if method and method.startswith('Network.webSocket'):
                        transport_tail.append({'method':method,'session':session,'opcode':p.get('response',{}).get('opcode')})
                        del transport_tail[:-20]
                    if method=='Network.webSocketFrameReceived':
                        frame=p['response']
                        if frame['opcode']==1:
                            try:data=json.loads(frame['payloadData'])
                            except (ValueError,TypeError):return
                            if isinstance(data,dict) and data.get('protocol_version')==1:
                                stamp=p['timestamp'];origin=stamp if origin is None else origin
                                records.append({'at':stamp-origin,'message':data})
                    if method=='Network.webSocketFrameSent' and p['response']['opcode']==2:
                        block=base64.b64decode(p['response']['payloadData']);pcm.append(block)
                        if not block:eof=True

                def call(method,params=None,session=None):
                    nonlocal serial
                    serial+=1;identifier=serial
                    msg={'id':identifier,'method':method,'params':params or {}}
                    if session:msg['sessionId']=session
                    ws.send(json.dumps(msg))
                    while identifier not in responses:
                        event(json.loads(ws.recv(timeout=20)))
                        # window.open can block Runtime.evaluate until its paused
                        # popup is resumed. Attach while awaiting this response.
                        if attached:attach_pending()
                    result=responses.pop(identifier)
                    if 'error' in result:raise RuntimeError('CDP command failed: '+method)
                    return result.get('result',{})

                def attach_pending():
                    nonlocal page_session,capture_session
                    while attached:
                        item=attached.pop(0);info=item['targetInfo'];session=item['sessionId']
                        target_sessions[info['targetId']]=session
                        if info['type']!='page':
                            call('Runtime.runIfWaitingForDebugger',session=session);continue
                        if '/capture' in info.get('url','') or info.get('openerId') in target_sessions:capture_session=session
                        elif page_session is None:page_session=session
                        call('Network.enable',session=session)
                        call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True},session)
                        call('Runtime.runIfWaitingForDebugger',session=session)

                def evaluate(expression):
                    result=call('Runtime.evaluate',{'expression':expression,'returnByValue':True,'awaitPromise':True,'userGesture':True},page_session)
                    if result.get('exceptionDetails'):raise RuntimeError('Operator evaluation failed')
                    return result.get('result',{}).get('value')

                call('Target.setDiscoverTargets',{'discover':True})
                call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True})
                call('Target.createTarget',{'url':'about:blank'})
                attach_pending()
                if page_session is None:raise RuntimeError('Could not attach Operator page before scripts')
                call('Page.navigate',{'url':args.url+'/operator'},page_session)
                started=False;stop_sent=False;clear_sent=False;deadline=time.monotonic()+expected_bytes/32000+120
                while time.monotonic()<deadline:
                    attach_pending()
                    ui=evaluate("globalThis.OperatorUI ? {ready:OperatorUI.authorized && !document.getElementById('start').disabled, state:OperatorUI.snapshot?.state, open:OperatorUI.snapshot?.session_open, owned:OperatorUI.snapshot?.owns_session, direction:OperatorUI.snapshot?.direction, outcome:OperatorUI.snapshot?.reliability?.outcome} : null")
                    save(out/'progress.json',{'operator':ui,'pcm_bytes':sum(len(b) for b in pcm),
                        'received_records':len(records),'capture_attached':capture_session is not None})
                    if not started and ui and ui['ready']:
                        evaluate("document.getElementById('direction').value='en-es'; document.getElementById('direction').onchange(); document.getElementById('start').click()")
                        started=True
                    total=sum(len(b) for b in pcm)
                    if ui and ui.get('state')=='live' and total>=expected_bytes/2 and not clear_sent:
                        evaluate("document.getElementById('clear').click()");clear_sent=True
                    if ui and ui.get('state')=='live' and total>=expected_bytes and not stop_sent:
                        evaluate("document.getElementById('stop').click()");stop_sent=True
                    if stop_sent and ui and ui.get('state')=='stopped' and not ui.get('open'):
                        # The status poll can complete before final WebSocket
                        # notifications reach this CDP connection. Do not close
                        # Chrome until the actual terminal frame is retained.
                        drain_until=time.monotonic()+10
                        while not eof or not any(r['message'].get('type')=='status' and r['message'].get('state')=='stopped' for r in records):
                            if time.monotonic()>=drain_until:raise TimeoutError('Final STOP frame missing from capture')
                            try:event(json.loads(ws.recv(timeout=.5)))
                            except TimeoutError:pass
                        if not ui.get('owned') or ui.get('outcome')!='complete':raise RuntimeError('Owner/complete STOP contract not observed')
                        save(out/'control_evidence.json',{'owns_session':True,'direction':ui['direction'],'outcome':ui['outcome'],
                            'start_via_operator':True,'stop_via_owner_control':stop_sent,'clear_via_owner_control':clear_sent,
                            'binary_eof':eof,'service_start':'not performed by collector'})
                        break
                    try:event(json.loads(ws.recv(timeout=.1)))
                    except TimeoutError:pass
                    if not production_guard.check()['safe']:
                        evaluate("document.getElementById('stop').click()")
                        raise RuntimeError('Production TRAD became active; lab capture stopped')
                else:raise TimeoutError('Lab capture did not finish normally')
        finally:
            save(out/'capture.partial.json',{'records':records,'binary_eof':eof,
                'source_wav_sha256':digest(source),'sent_samples':sum(len(b) for b in pcm)//2,
                'transport_tail':transport_tail,'session_sockets_observed':len(session_sockets),
                'policy':'Partial transport evidence; completion requires control_evidence and streaming_comparison'})
            with wave.open(str(out/'capture.partial_pcm.wav'),'wb') as partial:
                partial.setnchannels(1);partial.setsampwidth(2);partial.setframerate(16000);partial.writeframes(b''.join(pcm))
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=8)
    binary=b''.join(pcm)
    with wave.open(str(out/'capture.sent_pcm.wav'),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(binary)
    save(out/'capture.json',{'records':records,'source_wav_sha256':digest(source),'reference_sha256':digest(args.reference) if args.reference else None,
        'sent_pcm_sha256':hashlib.sha256(binary).hexdigest(),'sent_samples':len(binary)//2,'expected_source_samples':expected_bytes//2,
        'audio_caution':'Browser capture can add start/end latency or resampling differences; compare offline ASR on capture.sent_pcm.wav, not only original MP3'})
    result=analyze_capture(records,reference);save(out/'streaming_comparison.json',result)
    disagreement=result['raw_vs_ready']['wer']
    label='undefined (empty RAW)' if disagreement is None else f'{disagreement:.4%}'
    (out/'STREAMING.md').write_text(f"# Streaming / same-PCM protocol\n\nTranscript status: {result['transcript_status']}. RAW→READY normalized token disagreement {label}. This is not clinical WER.\n\nOffline on the exact capture.sent_pcm.wav is required before attributing causes. A matching reviewed fragment reference is required for accuracy WER; the full-conference reference must not be used for a cut fragment. No DeepL.\n",encoding='utf-8')
    return result

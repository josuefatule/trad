"""Real Chrome/Operator preparation regression. No mic, play, START or WLK.

Starts only a protected TRAD copy on 18010, closes owned processes in finally,
records no secrets/headers, uses no physical-attempt claims, preserves old runs.
"""
import argparse
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

from .cdp import install, ensure_document, evaluate, prepared, approve, release_capture
from .prepare import digest, private_path
from .tap import EvidenceWriter


class NoAudioApp:
    """Defense in depth only in this validation process, never physical capture."""
    def __init__(self,app,out):self.app,self.out,self.denied=app,Path(out),0
    async def __call__(self,scope,receive,send):
        if scope['type']=='websocket':
            self.denied+=1
            (self.out/'forbidden_websocket.json').write_text(json.dumps({'denied':self.denied}),encoding='utf-8')
            await send({'type':'websocket.close','code':4403});return
        return await self.app(scope,receive,send)


def server(out):
    from app.main import app,Settings
    import uvicorn
    settings=Settings()
    if settings.translation.enabled or settings.translation.deepl_auth_key:raise RuntimeError('DeepL must be OFF and key absent')
    uvicorn.run(NoAudioApp(app,out),host='127.0.0.1',port=18010,log_level='warning')


class Client:
    def __init__(self,ws,writer):
        self.ws,self.writer=ws,writer;self.serial=0;self.responses={};self.attached=[];self.sessions={}
        self.errors=[];self.network={'session_sockets':0,'mp3_requests':0};self.trace=[];self.script=''
        self.contexts={}
        self.effective_installations=[]
    def event(self,m):
        if 'id' in m:self.responses[m['id']]=m;return
        method=m.get('method');p=m.get('params',{});sid=m.get('sessionId')
        if method=='Target.attachedToTarget':self.attached.append(p)
        if method=='Runtime.executionContextCreated':self.contexts.setdefault(sid,set()).add(p['context']['id'])
        if method=='Runtime.executionContextDestroyed':self.contexts.get(sid,set()).discard(p['executionContextId'])
        if method=='Runtime.executionContextsCleared':self.contexts[sid]=set()
        if method=='Runtime.bindingCalled' and p.get('name')=='__m4bBinding':
            packet=json.loads(p['payload']);self.writer.submit(packet['rows'],(sid,p['executionContextId'],packet['id']))
        if method=='Runtime.exceptionThrown':
            # Keep only structural location, not arbitrary exception strings.
            d=p.get('exceptionDetails',{});self.errors.append({'line':d.get('lineNumber'),'url':d.get('url','').split('?')[0][-120:]})
        if method=='Network.webSocketCreated' and urlsplit(p.get('url','')).path=='/ws/session':self.network['session_sockets']+=1
        if method=='Network.requestWillBeSent' and urlsplit(p.get('request',{}).get('url','')).path.endswith('.mp3'):self.network['mp3_requests']+=1
    def fire(self,method,params=None,sid=None):
        self.serial+=1;identifier=self.serial;m={'id':identifier,'method':method,'params':params or {}}
        if sid:m['sessionId']=sid
        if method in {'Page.enable','Runtime.enable','Runtime.addBinding','Page.addScriptToEvaluateOnNewDocument','Page.navigate','Runtime.runIfWaitingForDebugger'}:
            self.trace.append({'method':method,'session':sid})
        self.ws.send(json.dumps(m))
        return identifier
    def wait(self,identifier,method):
        deadline=time.monotonic()+10
        while identifier not in self.responses:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('CDP command deadline: '+method)
            self.event(json.loads(self.ws.recv(timeout=remaining)))
            if self.attached:self.attach()
        result=self.responses.pop(identifier)
        if 'error' in result:raise RuntimeError('CDP failed: '+method)
        return result.get('result',{})
    def call(self,method,params=None,sid=None):return self.wait(self.fire(method,params,sid),method)
    def attach(self):
        while self.attached:
            a=self.attached.pop(0);sid=a['sessionId'];info=a['targetInfo']
            if info['type']=='page':
                self.sessions[sid]=info['targetId']
                install(self.call,sid,self.script,no_audio=True,validation_source=NO_AUDIO,fire=self.fire,wait=self.wait)
                self.call('Network.enable',sid=sid)
                self.call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True},sid)
            else:self.call('Runtime.runIfWaitingForDebugger',sid=sid)
    def pump(self):
        self.attach()
        while True:
            try:sid,context,ack=self.writer.acks.get_nowait()
            except queue.Empty:break
            if context not in self.contexts.get(sid,set()):continue
            self.call('Runtime.evaluate',{'expression':f'__m4bAck?.({ack})','contextId':context},sid)
        if self.writer.failed:raise RuntimeError('Evidence writer failed')
        try:self.event(json.loads(self.ws.recv(timeout=.03)))
        except TimeoutError:pass
    def ready(self,sid):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            self.pump()
            if ensure_document(self.call,sid,self.script,no_audio=True,validation_source=NO_AUDIO):
                self.effective_installations.append({'session':sid,'path':evaluate(self.call,sid)['path']})
            value=evaluate(self.call,sid)
            if prepared(value):return value
        raise RuntimeError('M4B_PREPARATION_FAILED: real-browser readiness not verified')


NO_AUDIO="""(() => {
  let eligible=location.port==='18010' && ['127.0.0.1','localhost'].includes(location.hostname);
  // Independent safety hooks must also cover the related initial document.
  try{eligible ||= location.href==='about:blank' && !!window.opener &&
    ['http://127.0.0.1:18010','http://localhost:18010'].includes(window.opener.location.origin);}catch{}
  if(!eligible)return;
  const existing=globalThis.__m4bNoAudioCounts;
  const count=existing || (globalThis.__m4bNoAudioCounts={gum:0,play:0,audio_context:0,session_socket:0,capture_start:0});
  // Observe at the receiver. Wrapping postMessage in the destination realm
  // changes MessageEvent.source and invalidates an opener/owner regression.
  if(globalThis.__m4bNoAudioDocument!==document){
  globalThis.__m4bNoAudioDocument=document;
  window.addEventListener('message',event=>{
    if(event.data?.type==='capture_start'){
      count.capture_start++;event.stopImmediatePropagation();
      // Booleans only: never serialize the operational token/device identifier.
      globalThis.__m4bNoAudioProtocol={source_is_opener:event.source===window.opener,
        same_origin:event.origin===location.origin,
        token_unchanged:event.data.token===window.opener?.OperatorUI?.token,
        device_unchanged:event.data.deviceId===window.opener?.document.getElementById('microphone')?.value,
        direction_unchanged:event.data.direction===window.opener?.OperatorUI?.directionId};
    }
  },true);
  }
  if(existing)return;
  // Installed before observers, so their identity checks remain meaningful.
  navigator.mediaDevices.getUserMedia=()=>{count.gum++;return Promise.reject(Error('M4B_NO_MICROPHONE'));};
  HTMLMediaElement.prototype.play=function(){count.play++;return Promise.reject(Error('M4B_NO_PLAYBACK'));};
  // No AudioContext is created by Operator/CAPTURE initialization.
  const Audio=globalThis.AudioContext;
  globalThis.AudioContext=class extends Audio {constructor(){count.audio_context++;throw Error('M4B_NO_AUDIO_CONTEXT');}};
  const Socket=globalThis.WebSocket;
  globalThis.WebSocket=class extends Socket {constructor(url,...args){
    if(new URL(url,location.href).pathname==='/ws/session'){count.session_socket++;throw Error('M4B_NO_SESSION');}
    super(url,...args);
  }};
  globalThis.__m4bNoAudioCounts=count;
})();"""


def status():
    base='http://127.0.0.1:18010'
    with urllib.request.urlopen(base+'/api/operator/bootstrap',timeout=3) as r:boot=json.load(r)
    req=urllib.request.Request(base+'/api/operator/status',headers={'X-Operator-Token':boot['control_token']})
    with urllib.request.urlopen(req,timeout=3) as r:s=json.load(r)
    return {'state':s['state'],'session_open':s['session_open'],'can_start':s['can_start'],'translator':s['translator']['state']}


def validate(plan_path,out):
    from .server import listening
    if any(listening(p) for p in (8000,8010,18000,18010)):raise RuntimeError('All ports must be free; never stop LIVE here')
    plan_path=Path(plan_path).resolve();plan=json.loads(plan_path.read_text(encoding='utf-8'));copy=Path(plan['copy']).resolve()
    for name,h in plan['original_sources'].items():
        if digest(copy/name)!=plan['modified_copy_only'].get(name,h):raise ValueError('Frozen copy changed: '+name)
    out=private_path(out);out.mkdir(parents=True,exist_ok=False)
    config={k:v for k,v in os.environ.items() if not k.startswith(('DEEPL_','TRANSLATION_','CAPTIONS_','SEGMENT_','RELIABILITY_','OPERATOR_','NORMALIZER_','CAPTION_','PYTHONPATH'))}
    config.update(plan['config']);config['CAPTIONS_LOG_DIR']=str(out/'server_logs')
    server_out=(out/'server.stdout.log').open('x');server_err=(out/'server.stderr.log').open('x')
    process=subprocess.Popen([str(Path('C:/live-captions/.venv/Scripts/python.exe')),'-m','trad_lab.m4b.validate_cdp','--server',str(out)],
        cwd=copy,env=config,stdout=server_out,stderr=server_err,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW)
    chrome=None;writer=None;c=None;result={'status':'running','server_launcher_pid':process.pid,'no_audio':True,'physical_claims_created':0}
    before_claims=sorted(p.name for p in plan_path.parent.glob('physical_attempt_*.claim'))
    try:
        deadline=time.monotonic()+20
        while True:
            try:s=status();break
            except Exception:
                if process.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Validation server startup failed')
                time.sleep(.1)
        assert s['translator']=='disabled' and not s['session_open']
        result['operator_before']=s
        profile=out/'chrome-profile'
        chrome=subprocess.Popen(['C:/Program Files/Google/Chrome/Application/chrome.exe','--headless=new','--disable-gpu','--disable-extensions',
            '--no-first-run','--deny-permission-prompts','--disable-background-networking','--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+15
        while not (profile/'DevToolsActivePort').exists():
            if time.monotonic()>deadline:raise RuntimeError('Chrome startup failed')
            time.sleep(.05)
        port,path=(profile/'DevToolsActivePort').read_text().splitlines()
        writer=EvidenceWriter(out/'browser')
        from websockets.sync.client import connect
        with connect(f'ws://127.0.0.1:{port}{path}',proxy=None,max_size=1048576) as ws:
            c=Client(ws,writer);c.script=Path(__file__).with_name('browser.js').read_text(encoding='utf-8')
            result['browser']=c.call('Browser.getVersion')['product']
            c.call('Target.setDiscoverTargets',{'discover':True})
            c.call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True});c.attach()
            if not c.sessions:c.call('Target.createTarget',{'url':'about:blank'});c.attach()
            first=next(iter(c.sessions));c.call('Page.navigate',{'url':'http://127.0.0.1:18010/operator'},first)
            initial=c.ready(first);assert initial['start_disabled'];approve(c.call,first,initial)
            c.pump();result['operator_initial']=evaluate(c.call,first)
            assert result['operator_initial']['start_disabled']
            # Bind the app's actual owner window without invoking START. The
            # parent barrier must retain the real capture_ready before the app
            # listener, even while child scripts/ACK have not been installed.
            old=set(c.sessions)
            c.call('Runtime.evaluate',{'expression':"captureWindow=window.open('/capture','m4b-noaudio-popup','popup,width=620,height=420'); captureWindow.requestedDirection=OperatorUI.directionId; void 0",'userGesture':True},first)
            deadline=time.monotonic()+10
            while set(c.sessions)==old:
                c.pump()
                if time.monotonic()>deadline:raise RuntimeError('Popup autoattach missing')
            popup=next(iter(set(c.sessions)-old));v=c.ready(popup);assert v['path']=='/capture'
            result['popup_before_approval']=v;assert not v['gate']['approved']
            assert c.call('Runtime.evaluate',{'expression':'window.opener!==null','returnByValue':True},popup)['result']['value']
            deadline=time.monotonic()+5
            while not evaluate(c.call,first)['gate']['capture_pending']:
                c.pump()
                if time.monotonic()>deadline:raise RuntimeError('Owner failed to retain real capture_ready')
            result['owner_holds_capture_ready']=True
            approve(c.call,popup,v)
            result['popup']=evaluate(c.call,popup)
            # No-audio mode forbids release even when child is now prepared.
            result['no_audio_release_rejected']=evaluate(c.call,first,
                "(()=>{try{__m4bGate.releaseCapture("+json.dumps(v['state']['page'])+");return false;}catch{return true;}})()")
            assert result['no_audio_release_rejected']
            # Reinstallation in an existing document must preserve wrappers,
            # page identity and the ACK, with no duplicate panel or observers.
            assert not ensure_document(c.call,popup,c.script,no_audio=True,validation_source=NO_AUDIO)
            assert evaluate(c.call,popup)['state']['page']==v['state']['page']
            # Exercise normal parent release without invoking START or the
            # child's session handler: independent receiver/native guards remain
            # installed and intercept the real app's capture_start before it.
            for sid in (first,popup):
                c.call('Runtime.evaluate',{'expression':'globalThis.__m4bNoAudio=false'},sid)
            release_capture(c.call,first,v['state']['page'])
            deadline=time.monotonic()+5
            while True:
                c.pump();protocol=evaluate(c.call,popup,'globalThis.__m4bNoAudioProtocol')
                if protocol:break
                if time.monotonic()>deadline:
                    result['release_timeout_diagnostic']={
                        'owner':evaluate(c.call,first),
                        'owner_binding':evaluate(c.call,first,"({bound:!!captureWindow,path:captureWindow?.location.pathname,capture_mode:OperatorUI.captureMode})"),
                        'child':evaluate(c.call,popup),
                        'child_counts':evaluate(c.call,popup,'globalThis.__m4bNoAudioCounts||null')}
                    raise RuntimeError('Normal owner release did not reach independent no-audio receiver')
            assert all(protocol.values())
            result['owner_release_intercepted_before_session']=protocol
            try:release_capture(c.call,first,v['state']['page'])
            except RuntimeError:result['duplicate_release_rejected']=True
            else:raise RuntimeError('Duplicate owner release allowed')
            for sid in (first,popup):
                c.call('Runtime.evaluate',{'expression':'globalThis.__m4bNoAudio=true'},sid)
            # Reload tests a new execution context and a fresh, blocked barrier.
            old_page=result['operator_initial']['state']['page'];c.call('Page.reload',{},first)
            deadline=time.monotonic()+10
            while True:
                c.pump();ensure_document(c.call,first,c.script,no_audio=True,validation_source=NO_AUDIO);v=evaluate(c.call,first)
                if v and (v.get('state') or {}).get('page')!=old_page and prepared(v):break
                if time.monotonic()>deadline:raise RuntimeError('Reload readiness missing')
            assert v['start_disabled'];approve(c.call,first,v);result['operator_reload']=evaluate(c.call,first)
            result['no_audio_counts']={}
            for sid in (first,popup):
                counts=c.call('Runtime.evaluate',{'expression':'__m4bNoAudioCounts','returnByValue':True},sid)['result']['value']
                expected_capture=1 if sid==popup else 0
                assert counts['capture_start']==expected_capture and all(n==0 for k,n in counts.items() if k!='capture_start')
                result['no_audio_counts'][sid]=counts
            # Diagnostic failure re-locks START and cannot be approved again.
            c.call('Runtime.evaluate',{'expression':"__m4bGate.fail('M4B_TEST_FAILURE')"},first);c.pump()
            failed=evaluate(c.call,first);assert failed['start_disabled'] and not prepared(failed)
            result['failure_gate_blocks_start']=True
            result['network']=c.network;assert not any(c.network.values());assert not c.errors
            result['javascript_exceptions']=c.errors;result['cdp_trace']=c.trace
            result['operator_after']=status();assert not result['operator_after']['session_open'] and result['operator_after']['translator']=='disabled'
            assert not (out/'forbidden_websocket.json').exists()
            result['status']='PASS'
            try:c.call('Browser.close')
            except Exception:pass
    except Exception as exc:
        result['status']='FAIL';result['error_type']=type(exc).__name__
        if c:
            result['failure_snapshots']=[]
            for sid in list(c.sessions):
                try:
                    result['failure_snapshots'].append({'session':sid,'state':evaluate(c.call,sid),
                        'no_audio_counts':evaluate(c.call,sid,'globalThis.__m4bNoAudioCounts||null')})
                except Exception:pass
        raise
    finally:
        if c:
            result['javascript_exceptions']=c.errors;result['cdp_trace']=c.trace;result['network']=c.network
            result['effective_document_installations']=c.effective_installations
        if writer:writer.close()
        if writer and (writer.path/'events.jsonl').exists():
            forbidden={'media_requested','track','pre','sent','first_audio_block','worklet_created','reference_playing','capture_socket_created'}
            kinds={json.loads(line)['kind'] for line in (writer.path/'events.jsonl').read_text(encoding='utf-8').splitlines()}
            result['forbidden_audio_events']=sorted(kinds & forbidden)
            if result['forbidden_audio_events']:result['status']='FAIL: audio-related event'
        if chrome:
            if chrome.poll() is None:chrome.terminate()
            chrome.wait(timeout=10)
        try:os.kill(process.pid,signal.CTRL_BREAK_EVENT);process.wait(timeout=12)
        except Exception:
            # Only our private process, never processes found by port/name.
            if process.poll() is None:process.terminate();process.wait(timeout=8)
        server_out.close();server_err.close()
        result['claims_unchanged']=before_claims==sorted(p.name for p in plan_path.parent.glob('physical_attempt_*.claim'))
        result['ports_free']={str(p):not listening(p) for p in (8000,8010,18000,18010)}
        if not all(result['ports_free'].values()):result['status']='FAIL: port still listening'
        (out/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    if result['status']!='PASS':raise RuntimeError(result['status'])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--server');p.add_argument('--plan');p.add_argument('--out');args=p.parse_args()
    if args.server:server(args.server)
    else:print(json.dumps(validate(args.plan,args.out),indent=2))

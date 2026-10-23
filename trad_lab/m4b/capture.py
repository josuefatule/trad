"""Visible manual Chrome collector. No fake microphone or automatic START.

Does not create services. Captures one session/attempt, retaining a bounded
disk stream, Python clock brackets and per-page acknowledgements.
"""
import json
from pathlib import Path
import queue
import shutil
import subprocess
import time
import urllib.request

from .prepare import private_path
from .tap import EvidenceWriter
from .cdp import install, ensure_document, evaluate, prepared, approve, reserve_attempt, release_capture


def capture(args):
    if args.authorization != 'M4-B aprobado hasta 3 sesiones': raise ValueError('Fresh human authorization required')
    plan = Path(args.plan).resolve(); data = json.loads(plan.read_text(encoding='utf-8'))
    from .server import listening
    if listening(8000) or listening(8010): raise RuntimeError('LIVE services must be closed manually first')
    base='http://127.0.0.1:18010'
    with urllib.request.urlopen(base+'/api/operator/bootstrap',timeout=3) as r: boot=json.load(r)
    req=urllib.request.Request(base+'/api/operator/status',headers={'X-Operator-Token':boot['control_token']})
    with urllib.request.urlopen(req,timeout=3) as r: state=json.load(r)
    del boot
    if state.get('translator',{}).get('state')!='disabled' or not state.get('can_start'): raise RuntimeError('Require disabled DeepL and idle Operator')
    # Preparation failure must not consume a physical attempt. Reserve only
    # after real observers, panel and writer roundtrip have all been verified.
    if all((plan.parent/f'physical_attempt_{i:02d}.claim').exists() for i in range(1,4)):
        raise RuntimeError('Three-attempt budget exhausted; request new authorization')
    i=None
    out=private_path(args.out);out.mkdir(parents=True,exist_ok=False)
    writer=EvidenceWriter(out/'browser')
    browser=shutil.which('chrome') or next((str(p) for p in [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')] if p.exists()),None)
    if not browser:writer.close();raise RuntimeError('Chrome/Edge unavailable')
    script=Path(__file__).with_name('browser.js').read_text(encoding='utf-8')
    profile=out/'chrome-profile'
    process=subprocess.Popen([browser,'--disable-gpu','--disable-extensions','--no-first-run','--no-default-browser-check',
        '--disable-background-networking','--disable-background-timer-throttling','--disable-renderer-backgrounding',
        '--remote-debugging-port=0','--user-data-dir='+str(profile),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    serial=0;responses={};attached=[];sessions={};terminal=False;terminal_at=None;session_ids=set();safe_to_close=False;owner=None
    media_started=False;script_errors=[];approved_pages={};preparation_started={}
    contexts={}
    try:
        active=profile/'DevToolsActivePort';deadline=time.monotonic()+20
        while not active.exists() and time.monotonic()<deadline:time.sleep(.05)
        lines=active.read_text().splitlines()
        from websockets.sync.client import connect
        with connect(f'ws://127.0.0.1:{lines[0]}{lines[1]}',proxy=None,max_size=1048576) as ws:
            def event(m):
                nonlocal terminal,terminal_at,media_started
                if 'id' in m:responses[m['id']]=m;return
                p=m.get('params',{});sid=m.get('sessionId')
                if m.get('method')=='Target.attachedToTarget':attached.append(p)
                if m.get('method')=='Runtime.executionContextCreated':contexts.setdefault(sid,set()).add(p['context']['id'])
                if m.get('method')=='Runtime.executionContextDestroyed':contexts.get(sid,set()).discard(p['executionContextId'])
                if m.get('method')=='Runtime.executionContextsCleared':contexts[sid]=set()
                if m.get('method')=='Runtime.exceptionThrown':
                    d=p.get('exceptionDetails',{});urls=[d.get('url','')]+[f.get('url','') for f in d.get('stackTrace',{}).get('callFrames',[])]
                    if any(u.startswith('m4b-') for u in urls):
                        script_errors.append({'kind':'instrumentation_exception','code':'M4B_SCRIPT_EXCEPTION','line':d.get('lineNumber')})
                        writer.submit([script_errors[-1]])
                if m.get('method')=='Runtime.bindingCalled' and p.get('name')=='__m4bBinding':
                    packet=json.loads(p['payload'])
                    rows=packet['rows']
                    for row in rows:
                        if row.get('session_id'):session_ids.add(row['session_id'])
                        if row['kind']=='terminal_observed':terminal=True;terminal_at=time.monotonic()
                        if row['kind'] in {'track','worklet_created','pre','sent'}:media_started=True
                        row['collector_py_ns']=time.perf_counter_ns()
                    if len(session_ids)>1:raise RuntimeError('One session per collector; stop and preserve evidence')
                    writer.submit(rows,(sid,p['executionContextId'],packet['id']))
            def fire(method,params=None,sid=None):
                nonlocal serial
                serial+=1;identifier=serial;msg={'id':identifier,'method':method,'params':params or {}}
                if sid:msg['sessionId']=sid
                ws.send(json.dumps(msg))
                return identifier
            def wait(identifier,method):
                command_deadline=time.monotonic()+15
                while identifier not in responses:
                    remaining=command_deadline-time.monotonic()
                    if remaining<=0:raise TimeoutError('CDP command deadline: '+method)
                    event(json.loads(ws.recv(timeout=remaining)))
                    if attached:attach()
                result=responses.pop(identifier)
                if 'error' in result:raise RuntimeError('CDP failed: '+method)
                return result.get('result',{})
            def call(method,params=None,sid=None):return wait(fire(method,params,sid),method)
            def attach():
                while attached:
                    a=attached.pop(0);sid=a['sessionId'];info=a['targetInfo']
                    if info['type']=='page':
                        sessions[sid]=info['targetId']
                        install(call,sid,script,fire=fire,wait=wait)
                        call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True},sid)
                    else:call('Runtime.runIfWaitingForDebugger',sid=sid)
            call('Target.setDiscoverTargets',{'discover':True})
            call('Target.setAutoAttach',{'autoAttach':True,'waitForDebuggerOnStart':True,'flatten':True})
            attach()
            if not sessions:call('Target.createTarget',{'url':'about:blank'});attach()
            first=next(iter(sessions));call('Page.navigate',{'url':base+'/operator'},first)
            def acknowledgements():
                while True:
                    try:sid,context,ack=writer.acks.get_nowait()
                    except queue.Empty:break
                    if context not in contexts.get(sid,set()):continue
                    call('Runtime.evaluate',{'expression':f'globalThis.__m4bAck?.({ack})','contextId':context},sid)
            ready_deadline=time.monotonic()+10
            while True:
                attach();acknowledgements()
                if writer.failed or script_errors:raise RuntimeError('M4B_PREPARATION_FAILED: writer/script error; no attempt consumed')
                ensure_document(call,first,script)
                value=evaluate(call,first)
                if prepared(value):break
                if time.monotonic()>ready_deadline:raise RuntimeError('M4B_PREPARATION_FAILED: observers/panel/writer ACK missing; no attempt consumed')
                try:event(json.loads(ws.recv(timeout=.05)))
                except TimeoutError:pass
            approve(call,first,value);approved_pages[first]=value['state']['page']
            (out/'preparation.json').write_text(json.dumps({'ready':True,'attempt':None,'operator':value,'writer_roundtrip':True,'capture_pending':True},indent=2),encoding='utf-8')
            print('M4-B Operator preparado. Selección/START manual; el propietario retiene capture_ready hasta preparar CAPTURE. Sin claim todavía. Máximo 240 s.',flush=True)
            deadline=time.monotonic()+240;last_sync=0
            while time.monotonic()<deadline:
                attach()
                acknowledgements()
                if writer.failed:raise RuntimeError('Evidence invalid: '+writer.failed+'; use normal STOP before closing Chrome')
                if script_errors:raise RuntimeError('M4B_SCRIPT_EXCEPTION: instrumentation failed; stop normally')
                for sid in list(sessions):
                    ensure_document(call,sid,script)
                    value=evaluate(call,sid)
                    if not value or value['path'] not in {'/operator','/capture'}:continue
                    page=(value.get('state') or {}).get('page')
                    if approved_pages.get(sid)==page and page:
                        if not prepared(value):raise RuntimeError('M4B_INSTRUMENTATION_LOST: stop normally')
                    elif prepared(value):
                        approve(call,sid,value);approved_pages[sid]=page
                        preparation_started.pop(sid,None)
                        writer.submit([{'kind':'page_prepared','page':page,'surface':value['path']}])
                    else:
                        since=preparation_started.setdefault(sid,time.monotonic())
                        if time.monotonic()-since>5:raise RuntimeError('M4B_POPUP_PREPARATION_FAILED: owner must retain capture_ready; verify status')
                if i is None:
                    owner_ready=evaluate(call,first)
                    if owner_ready and owner_ready.get('gate',{}).get('capture_pending'):
                        children=[(sid,evaluate(call,sid)) for sid in sessions if sid!=first]
                        children=[(sid,v) for sid,v in children if v and v.get('path')=='/capture']
                        if len(children)>1:raise RuntimeError('M4B_MULTIPLE_CAPTURE_WINDOWS: no attempt consumed')
                        if children and prepared(children[0][1]):
                            child_sid,child_ready=children[0]
                            i=reserve_attempt(plan,args.out,owner_ready,child_ready)
                            release_capture(call,first,child_ready['state']['page'])
                            (out/'capture_preparation.json').write_text(json.dumps({'ready':True,'attempt':i,
                                'operator':owner_ready,'capture':child_ready,'writer_roundtrip':True,'owner_released':True},indent=2),encoding='utf-8')
                            print(f'M4-B intento {i:02d}: CAPTURE preparado con ACK; capture_ready liberado al propietario.',flush=True)
                if time.monotonic()-last_sync>2:
                    last_sync=time.monotonic()
                    for sid in list(sessions):
                        before=time.perf_counter_ns()
                        result=call('Runtime.evaluate',{'expression':'({timeOrigin:performance.timeOrigin,now:performance.now(),visibility:document.visibilityState,state:globalThis.__m4bState?.()})','returnByValue':True},sid)
                        after=time.perf_counter_ns();value=result.get('result',{}).get('value')
                        if value:writer.submit([{'kind':'clock_bracket','py_before_ns':before,'py_after_ns':after,'page_clock':value}])
                if terminal and time.monotonic()-terminal_at>2:
                    # Verify application STOP plus logger queue/ACK drain on each page.
                    states=[]
                    for sid in sessions:
                        r=call('Runtime.evaluate',{'expression':'''({diagnostic:globalThis.__m4bState?.(),
                            operator:location.pathname==='/operator' && globalThis.OperatorUI?.snapshot ? {
                            owns_session:OperatorUI.snapshot.owns_session,session_open:OperatorUI.snapshot.session_open,
                            state:OperatorUI.snapshot.state,outcome:OperatorUI.snapshot.reliability?.outcome,
                            direction:OperatorUI.snapshot.direction} : null})''','returnByValue':True},sid)
                        v=r.get('result',{}).get('value')
                        if v:
                            if v.get('diagnostic'):states.append(v['diagnostic'])
                            if v.get('operator'):owner=v['operator']
                    if (owner and owner.get('owns_session') and not owner.get('session_open') and owner.get('state')=='stopped'
                            and states and all(not v['pending'] and not v['inflight'] and not v['failed'] for v in states)):
                        safe_to_close=True;break
                try:event(json.loads(ws.recv(timeout=.05)))
                except TimeoutError:pass
            else:raise TimeoutError('Manual attempt timeout; preserve partial evidence and STOP normally')
            (out/'completion.json').write_text(json.dumps({'terminal_observed':terminal,'sessions':sorted(session_ids),
                'attempt':i,'owner':owner,'manual_start_stop':True,'microphone':'real getUserMedia; no fake audio flags'},indent=2),encoding='utf-8')
    except Exception as exc:
        (out/'preparation_or_capture_error.json').write_text(json.dumps({'error_type':type(exc).__name__,
            'diagnostic':str(exc)[:200] if str(exc).startswith('M4B_') else 'Collector failure; inspect local logs',
            'physical_claim':i,'media_started':media_started},indent=2),encoding='utf-8')
        raise
    finally:
        writer.close()
        # Do not close CAPTURE while it might still be sending: on a failure the
        # browser is deliberately left visible for the owner to STOP normally.
        if safe_to_close or not media_started:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=8)
            # This directory was created for this attempt, inside the verified
            # new private output. Never retain browser auth storage in evidence.
            if profile.resolve().is_relative_to(out) and profile.name=='chrome-profile':
                try:shutil.rmtree(profile)
                except OSError:print('Perfil privado todavía bloqueado; cerrar Chrome y retirar solo este perfil del ensayo.',flush=True)
        else:
            print('Intento incompleto: navegador conservado. Pulsa STOP y espera EOF; no inicies otra sesión.',flush=True)

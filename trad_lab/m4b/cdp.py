"""Shared CDP installation and preparation checks, including real-browser tests."""
from pathlib import Path


def scripts(source,*,no_audio=False,validation_source=None):
    guard=Path(__file__).with_name('guard.js').read_text(encoding='utf-8')
    if no_audio:guard='globalThis.__m4bNoAudio=true;\n'+guard
    result=[guard+'\n//# sourceURL=m4b-guard.js']
    if validation_source:
        if not no_audio:raise ValueError('Validation guards require no_audio mode')
        result.append(validation_source+'\n//# sourceURL=m4b-no-audio.js')
    return result+[source+'\n//# sourceURL=m4b-observers.js']


def install(call,sid,source,*,no_audio=False,validation_source=None,fire=None,wait=None):
    # Chromium accepts addScriptToEvaluateOnNewDocument while Page is disabled,
    # but did not execute it on navigation in the reproduced failing sequence.
    requests=[]
    def command(method,params=None):
        if fire:requests.append((fire(method,params,sid),method))
        else:call(method,params,sid)
    command('Page.enable')
    command('Runtime.enable')
    command('Runtime.addBinding',{'name':'__m4bBinding'})
    for script in scripts(source,no_audio=no_audio,validation_source=validation_source):
        command('Page.addScriptToEvaluateOnNewDocument',{'source':script})
    if fire:
        # An autoattached popup can hold window.open until it is resumed.
        # Page.enable itself may wait for that popup's initial frame. Queue all
        # installation commands in order, then resume BEFORE awaiting replies.
        command('Runtime.runIfWaitingForDebugger')
        for identifier,method in requests:wait(identifier,method)


def ensure_document(call,sid,source,*,no_audio=False,validation_source=None):
    """Related popups may reuse the initial about:blank global/context.

    New-document scripts then ran with an ineligible URL and returned early.
    Install idempotently in the effective document BEFORE owner release; never
    treat late attachment as proof of observation before this preparation.
    """
    state=evaluate(call,sid,"""({eligible:location.port==='18010' &&
        ['127.0.0.1','localhost'].includes(location.hostname) &&
        ['/operator','/capture'].includes(location.pathname),
        installed:!!globalThis.__m4bGate && !!globalThis.__m4bState})""")
    if not state or not state.get('eligible') or state.get('installed'):return False
    result=call('Runtime.evaluate',{'expression':'\n'.join(scripts(source,no_audio=no_audio,validation_source=validation_source))},sid)
    if result.get('exceptionDetails'):raise RuntimeError('M4B_SCRIPT_EXCEPTION: effective-document installation failed')
    return True


def release_capture(call,owner_sid,page):
    import json
    result=call('Runtime.evaluate',{'expression':'__m4bGate.releaseCapture('+json.dumps(page)+')','returnByValue':True},owner_sid)
    if result.get('exceptionDetails') or result.get('result',{}).get('value') is not True:
        raise RuntimeError('M4B_OWNER_BARRIER_FAILED: capture_ready not released')


SNAPSHOT="""({path:location.pathname,complete:document.readyState==='complete',
    state:globalThis.__m4bState?.(),gate:globalThis.__m4bGate?.state(),
    panel:!!document.getElementById('m4b-state'),start_disabled:document.getElementById('start')?.disabled,
    operator:!!globalThis.OperatorUI,authorized:!!globalThis.OperatorUI?.authorized})"""


def prepared(value):
    if not value or value.get('path') not in {'/operator','/capture'}:return False
    state=value.get('state') or {}
    observers=state.get('observers') or {}
    return bool(value.get('complete') and value.get('operator') and value.get('gate')
        and value['gate'].get('owner_barrier') and not value['gate'].get('failed') and state.get('dom_ready') and state.get('ready_acknowledged') and not state.get('failed')
        and set(observers)=={'media','worklet','worker','websocket','dom','controls'} and all(observers.values())
        and (value['path']!='/operator' or value.get('panel')))


def approve(call,sid,value):
    if not prepared(value):raise RuntimeError('M4B_PREPARATION_FAILED: observers/panel/writer ACK missing; START remains blocked')
    import json
    result=call('Runtime.evaluate',{'expression':'__m4bGate.approve('+json.dumps(value['state']['page'])+')','returnByValue':True},sid)
    if result.get('exceptionDetails') or result.get('result',{}).get('value') is not True:
        raise RuntimeError('M4B_PREPARATION_FAILED: stale document or gate refused readiness')


def evaluate(call,sid,expression=SNAPSHOT):
    result=call('Runtime.evaluate',{'expression':expression,'returnByValue':True},sid)
    if result.get('exceptionDetails'):raise RuntimeError('M4B_SCRIPT_EXCEPTION: preparation state unavailable')
    return result.get('result',{}).get('value')


def reserve_attempt(plan,out,value,capture_value=None):
    """No physical budget is consumed by missing/failed instrumentation."""
    if (not prepared(value) or value['path']!='/operator' or not prepared(capture_value)
            or capture_value['path']!='/capture'):
        raise RuntimeError('M4B_PREPARATION_FAILED: both documents required; no physical attempt consumed')
    for candidate in range(1,4):
        try:
            with (Path(plan).parent/f'physical_attempt_{candidate:02d}.claim').open('x') as f:f.write(str(out))
            return candidate
        except FileExistsError:continue
    raise RuntimeError('Three-attempt budget exhausted')

"""Immutable new phase-A copy from the sealed C1 candidate."""
import json
from pathlib import Path
import shutil
from trad_lab.audio import digest
from trad_lab.m5b.prepare import verify as verify_c1

ROOT=Path('C:/live-captions')
BASE=ROOT/'logs/trad_lab/m5c1_20261021T113447Z/environment_c1_final/plan.json'
BASE_SHA='0aa1745e70949fc0facd04ba551c3dcdd955bc07675916a38bfca9badf521425'


def verify(path):
    path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8'));copy=Path(data['copy']).resolve()
    if not copy.is_relative_to(ROOT/'logs/trad_lab') or copy.name!='copy':raise ValueError('Invalid lab path')
    if (data['phase'],data['backend_port'],data['trad_port'],data['deepl_enabled'],data['microphone_enabled'])!=('M5-C2-A',18000,18010,False,True):raise ValueError('Phase A policy changed')
    if data['resampler_sha256']!=digest(copy/'app/static/m5c_resampler.js'):raise ValueError('FIR selection changed')
    for name,sha in data['manifest'].items():
        p=(copy/name).resolve()
        if not p.is_relative_to(copy) or digest(p)!=sha:raise ValueError('Frozen source changed: '+name)
    actual={p.relative_to(copy).as_posix() for p in copy.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.runtime' not in p.parts}
    if actual!=set(data['manifest']):raise ValueError('Unmanifested source')
    return data


def prepare(out):
    assert digest(BASE)==BASE_SHA;old=verify_c1(BASE)
    out=Path(out).resolve();assert out.is_relative_to(ROOT/'logs/trad_lab');out.mkdir(parents=True,exist_ok=False);copy=out/'copy'
    for name,sha in old['manifest'].items():
        src=Path(old['copy'])/name;dst=copy/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        assert digest(src)==digest(dst)==sha
    for src in (ROOT/'trad_lab/m5c2').glob('*'):
        if src.is_file():
            dst=copy/'trad_lab/m5c2'/src.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    def patch(name,old,new):
        p=copy/name;s=p.read_text(encoding='utf-8');assert s.count(old)==1,(name,old);p.write_text(s.replace(old,new),encoding='utf-8')
    for name in ('configure_environment','provider_from_config','install as install_c1'):
        patch('app/main.py','from trad_lab.m5c.runtime import '+name,'from trad_lab.m5c2.runtime import '+name)
    shutil.copyfile(ROOT/'trad_lab/m5c2/evidence.js',copy/'app/static/m5c2_evidence.js')
    shutil.copyfile(ROOT/'trad_lab/m5c2/dom.js',copy/'app/static/m5c2_dom.js')
    patch('app/templates/m5c_capture.html','<script src="/static/m5c_physical_core.js">','<script src="/static/m5c2_evidence.js"></script><script src="/static/m5c_physical_core.js">')
    patch('app/templates/m5c_capture.html','Ruta preparada; micrófono bloqueado en M5-C1.','ENSAYO A · FIR127 seleccionado · DeepL OFF. Abrir micrófono solo bajo supervisión.')
    patch('app/templates/m5c_capture.html','<pre id="status">','<output id="level">Señal: pendiente</output><pre id="status">')
    patch('app/templates/operator.html','</head>','<script defer src="/static/m5c2_dom.js"></script></head>')
    patch('app/static/operator.js','$("refresh").onclick = () => microphones(true)',
          '$("refresh").onclick = () => microphones(false)')
    patch('app/templates/operator.html','Permitir / actualizar','Actualizar dispositivos (sin abrir micrófono)')
    patch('app/static/m5b_diagnostics.js','M5-B experimental · PCM de archivo · DeepL OFF','M5-C2 A · CAPTURE físico · DeepL OFF')
    for name in ('app/templates/operator.html','app/templates/overlay.html'):
        patch(name,'M5-C1 · SIMULACIÓN · NO USO CLÍNICO','M5-C2 A · ASR REAL · DEEPL OFF · ENSAYO')
    # Only observations and post-terminal private upload; same PCM/credit/worker.
    name='app/static/m5c_capture.js'
    patch(name,"const q=new M5CPhysical.PCMQueue();","const q=new M5CPhysical.PCMQueue();\n  const trace=globalThis.M5C2Trace;globalThis.M5C2_EVIDENCE_FAILURE=e=>error(e);")
    patch(name,"function error(e){if(failed)return;failed=true;","function error(e){if(failed)return;failed=true;try{trace.record({kind:'failure',error_name:e.name,reason:String(e.message).slice(0,200)});}catch{}trace.finish(true).catch(()=>{});")
    patch(name,'socket.send(buffer);timer=',"socket.send(buffer);trace.binary('sent',buffer,{sequence:q.pending.frame_sequence,eof:false});timer=")
    patch(name,"socket.send(new ArrayBuffer(0));status.textContent=", "socket.send(new ArrayBuffer(0));trace.binary('sent',new ArrayBuffer(0),{sequence:q.sequence,eof:true});status.textContent=")
    patch(name,'if(stopping||failed)return;stopping=true;',"if(stopping||failed)return;trace.record({kind:'stop'});stopping=true;")
    patch(name,'context=new AudioContext();',"trace.record({kind:'track',device_label:track.label,device_exact:true,settings:Object.fromEntries(Object.entries(track.getSettings()).filter(([k])=>['sampleRate','channelCount','echoCancellation','autoGainControl','noiseSuppression','latency'].includes(k)))});\n      context=new AudioContext();trace.record({kind:'context',sample_rate:context.sampleRate});")
    patch(name,'session=m.session_id;',"session=m.session_id;trace.start(session,()=>opener?.OperatorUI?.token||owner);")
    patch(name,'const m=e.data;if(m.error)throw Error(m.error);q.append(m.buffer);',"const m=e.data;if(m.error)throw Error(m.error);trace.record({kind:'worker',bytes:m.buffer.byteLength,ack:m.ack,flushed:!!m.flushed,metadata:m.metadata});q.append(m.buffer);")
    patch(name,"else worker.postMessage({command:'record',...m},[m.buffer]);", "else {const values=new Float32Array(m.buffer);let energy=0,peak=0,clipped=0;for(const x of values){energy+=x*x;peak=Math.max(peak,Math.abs(x));if(Math.abs(x)>=.999)clipped++;}const rms=Math.sqrt(energy/values.length);const level=document.getElementById('level');if(level)level.textContent='Señal: '+(rms?20*Math.log10(rms):-120).toFixed(1)+' dBFS · pico '+peak.toFixed(3)+' · clipping '+clipped;trace.binary('pre',m.buffer,{sequence:m.sequence,first_sample:m.first_sample,samples:m.samples,channels:m.channels,sample_rate:m.sample_rate,rms,peak,clipped});worker.postMessage({command:'record',...m},[m.buffer]);}")
    patch(name,'clearTimeout(timer);q.credit(m);pump();',"clearTimeout(timer);trace.record({kind:'ack',sequence:m.frame_sequence,bytes:m.bytes,received_bytes:m.received_bytes,sha256:m.sha256});q.credit(m);pump();")
    patch(name,"if(m.type==='asr'&&m.payload?.type==='ready_to_stop')terminal=true;", "if(m.type==='asr'&&m.payload?.type==='ready_to_stop'){terminal=true;trace.record({kind:'asr',event:'ready_to_stop',tail:m.payload.unconfirmed_eof_tail});}")
    end="if(m.type==='status'&&m.state==='stopped')status.textContent=JSON.stringify({transport:m.completion,asr:m.experimental_asr,accepted:q.accepted,sent:q.sent,acked:q.acked,terminal,peak_pcm_bytes:q.peak,dsp:dspMetadata},null,2);"
    patch(name,end,"if(m.type==='status'&&m.state==='stopped'){const result={transport:m.completion,asr:m.experimental_asr,accepted:q.accepted,sent:q.sent,acked:q.acked,terminal,peak_pcm_bytes:q.peak,dsp:dspMetadata};trace.record({kind:'terminal',result});status.textContent='Guardando evidencia; no cerrar CAPTURE';result.evidence=await trace.finish(false);status.textContent=JSON.stringify(result,null,2);}")
    manifest={p.relative_to(copy).as_posix():digest(p) for p in copy.rglob('*') if p.is_file()}
    data={**old,'copy':str(copy),'manifest':manifest,'phase':'M5-C2-A','base_plan':str(BASE),'base_plan_sha256':BASE_SHA,
          'microphone_enabled':True,'deepl_enabled':False,'mock_translation':False,'B_authorized':False,
          'resampler_selection':'Explicitly selected FIR127 for supervised A only; ASR differences acknowledged for review, no medical improvement claim',
          'resampler_sha256':digest(copy/'app/static/m5c_resampler.js'),'human_authorization':'User authorized C2-A only; presence and physical setup confirmation before CAPTURE',
          'services_started':False,'evidence_max_json_bytes':67108864}
    (out/'plan.json').write_text(json.dumps(data,indent=2),encoding='utf-8');verify(out/'plan.json');return data


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps({'files':len(prepare(a.out)['manifest'])}))

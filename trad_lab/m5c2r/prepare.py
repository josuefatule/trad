"""New immutable repair revision. Never patch LIVE or previous copies."""
import json
from pathlib import Path
import shutil
from trad_lab.audio import digest
from trad_lab.m5c2b.prepare import verify as verify_b

ROOT = Path('C:/live-captions')
BASE = ROOT/'logs/trad_lab/m5c2b_20261021T130251Z/environment_b_ready/plan.json'
BASE_SHA = '26e105465c74de6719bbfaf63b6b2172267f05ccc06564648d543e37f60fd330'


def verify(path):
    path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8'));copy=Path(data['copy']).resolve()
    if not copy.is_relative_to(ROOT/'logs/trad_lab') or copy.name!='copy':raise ValueError('Lab copy required')
    if (data['phase'],data['backend_port'],data['trad_port'],data['caption_mode'])!=('M5-C2-B-R1',18000,18010,'timed_queue'):raise ValueError('Repair policy changed')
    if digest(BASE)!=BASE_SHA:raise ValueError('Historical B plan changed')
    old=verify_b(BASE)
    for name,sha in data['manifest'].items():
        p=(copy/name).resolve()
        if not p.is_relative_to(copy) or digest(p)!=sha:raise ValueError('Frozen source changed: '+name)
    actual={p.relative_to(copy).as_posix() for p in copy.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.runtime' not in p.parts}
    if actual!=set(data['manifest']):raise ValueError('Unmanifested source')
    protected=[n for n in old['manifest'] if n.startswith(('trad_lab/m4c/','trad_lab/m5a/','trad_lab/m5b/','app/asr/','app/segmentation/')) or 'resampl' in n or n.endswith(('m5c_worker.js','m5c_worklet.js','m5c_physical_core.js','transcript_state.py'))]
    if any(data['manifest'].get(n)!=old['manifest'][n] for n in protected):raise ValueError('Protected ASR, DSP, transport or segmentation source changed')
    if data['profile']!=old['profile']:raise ValueError('ASR profile changed')
    return data


def prepare(out):
    assert digest(BASE)==BASE_SHA;old=verify_b(BASE)
    out=Path(out).resolve();assert out.is_relative_to(ROOT/'logs/trad_lab')
    out.mkdir(parents=True,exist_ok=False);copy=out/'copy'
    for name,sha in old['manifest'].items():
        src=Path(old['copy'])/name;dst=copy/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);assert digest(dst)==sha
    for src in (ROOT/'trad_lab/m5c2r').glob('*'):
        if src.is_file():
            dst=copy/'trad_lab/m5c2r'/src.name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    def patch(name,before,after):
        p=copy/name;s=p.read_text(encoding='utf-8');assert s.count(before)==1,(name,before);p.write_text(s.replace(before,after),encoding='utf-8')
    patch('app/main.py','from trad_lab.m5c2b.runtime import configure_environment','from trad_lab.m5c2r.runtime import configure_environment')
    patch('app/main.py','from trad_lab.m5c2b.runtime import install as install_c1','from trad_lab.m5c2r.runtime import install as install_c1')
    shutil.copyfile(ROOT/'trad_lab/m5c2r/evidence.js',copy/'app/static/m5c2_evidence.js')
    # ACK includes the actual writer counter, avoiding client/Python JSON size assumptions.
    patch('trad_lab/m5c2/runtime.py',"'server_received_ns':received,'server_written_ns':time.perf_counter_ns()}","'server_received_ns':received,'server_written_ns':time.perf_counter_ns(),'writer_json_bytes':writer.total}")
    name='app/static/m5c_capture.js'
    patch(name,'pumping=false,dspMetadata=null;','pumping=false,dspMetadata=null,evidenceFailed=false;')
    patch(name,'globalThis.M5C2_EVIDENCE_FAILURE=e=>error(e);',"globalThis.M5C2_EVIDENCE_FAILURE=e=>{evidenceFailed=true;status.textContent='REGISTRO INCOMPLETO: '+e.message+' · drenando audio/EOF';finish();};")
    patch(name,"trace.start(session,()=>opener?.OperatorUI?.token||owner);","trace.start(session,()=>opener?.OperatorUI?.token);")
    # Guard all native-message callbacks as well as making trace methods non-throwing.
    patch(name,"node.port.onmessage=e=>{\n              const m=e.data;","node.port.onmessage=e=>{\n              try{const m=e.data;")
    patch(name,"            };\n            source=context.createMediaStreamSource", "              }catch(e){error(e);}\n            };\n            source=context.createMediaStreamSource")
    patch(name,'result.evidence=await trace.finish(false);',"result.evidence=await trace.finish(evidenceFailed);result.experiment_complete=result.transport==='complete'&&terminal&&result.evidence.evidence_complete&&!result.evidence.capture_failed;")
    # Finish is safe even if recording failed. Keep original PCM/credit/flush logic.
    # Select original timed renderer; fail visibly instead of discarding old queued pages.
    name='app/static/caption_renderer.js'
    before='''      while (this.queue.length > this.config.visual_queue_max ||
             (this.queue.length > 1 && duration() > this.config.max_backlog_ms)) {
        this.queue.shift(); dropped++;
      }
      if (dropped) this.report("queue_overflow", dropped);'''
    after='''      if (this.queue.length > this.config.visual_queue_max ||
          (this.queue.length > 1 && duration() > this.config.max_backlog_ms)) {
        const pending = this.queue.length;
        this.clear(); this.presentationFailed = true;
        this.report("queue_overflow", pending); return;
      }'''
    patch(name,before,after)
    # The above text occurs in both modes; patch only the timed class prefix.
    p=copy/name;s=p.read_text();prefix,suffix=s.split('  class PersistentCaptionRenderer',1)
    prefix=prefix.replace('      this.seen = caption.sequence;','      if (this.presentationFailed) return;\n      this.seen = caption.sequence;')
    prefix=prefix.replace('      let dropped = 0;\n      // Bound both frame count and estimated display backlog, keeping the newest.', '      // Bound memory and reading backlog; suspend visibly instead of truncating pages.')
    prefix=prefix.replace('      this.generation++; this.cancel(this.timer);','      this.presentationFailed = false;\n      this.generation++; this.cancel(this.timer);')
    prefix=prefix.replace('    enqueue(caption, snapshotRemainingMs', '    failPresentation(reason, count) {\n      this.clear(); this.presentationFailed = true; this.report(reason, count);\n    }\n    enqueue(caption, snapshotRemainingMs')
    prefix=prefix.replace('this.report("oversize", 1); return;', 'this.failPresentation("oversize", 1); return;')
    prefix=prefix.replace('this.report(split.reason, 1); return;', 'this.failPresentation(split.reason, 1); return;')
    prefix=prefix.replace('          this.report("queue_overflow", 1); continue;','          const pending = this.queue.length + 1;\n          this.clear(); this.presentationFailed = true;\n          this.report("queue_overflow", pending); return;')
    p.write_text(prefix+'  class PersistentCaptionRenderer'+suffix,encoding='utf-8')
    # Make an actual presentation failure visible on the otherwise transparent overlay.
    patch('app/static/overlay.js','    console.warn("overlay_display_drop", {reason, count});',"    console.warn(\"overlay_display_drop\", {reason, count});\n    if(['queue_overflow','oversize','unreadable_token'].includes(reason)){element.hidden=false;element.classList.add('visible');element.textContent='SUBTÍTULOS SUSPENDIDOS · presentación incompleta · avisar al operador';}")
    patch('app/static/overlay.js','      if (renderer.current || renderer.queue.length) report("queue_overflow", renderer.queue.length + 1);', '      if (renderer.current || renderer.queue.length) {renderer.failPresentation("queue_overflow", renderer.queue.length + 1);renderer.config = effective();return;}')
    # Additional control evidence; no auth/control behavior changes.
    patch('app/static/m5c_controls.js',"hide.textContent='OCULTAR subtítulos';","hide.textContent='OCULTAR subtítulos';hide.id='m5c-hide';")
    patch('app/static/m5c_controls.js',"resume.textContent='REANUDAR: solo resultados nuevos';","resume.textContent='REANUDAR: solo resultados nuevos';resume.id='m5c-resume';")
    patch('app/static/m5c_controls.js',"state.textContent='Estado de ocultación no medido';","state.textContent='Estado de ocultación no medido';state.id='m5c-presentation-state';")
    patch('app/static/m5c2_dom.js',"['partial','confirmed','pending','ready','english','last-caption']","['partial','confirmed','pending','ready','english','last-caption','m5c-presentation-state']")
    patch('app/static/m5c2_dom.js',"['start','stop','clear']","['start','stop','clear','m5c-hide','m5c-resume']")
    p=copy/'app/static/m5c2_dom.js';s=p.read_text();s=s.replace("  for(const id of ['partial'", "  add('control',{action:'operator_document_ready'});\n  for(const id of ['partial'",1);p.write_text(s,encoding='utf-8')
    patch('app/static/m5c2_dom.js',"  add('control',{action:'operator_document_ready'});", "  api.record=add;\n  add('control',{action:'operator_document_ready'});")
    patch('app/static/m5c_controls.js','      display(hidden);',"      display(hidden);globalThis.M5C2_DOM?.record('control',{action:hidden?'hide_confirmed':'resume_confirmed',success:true,session_id:status.session_id});")
    manifest={p.relative_to(copy).as_posix():digest(p) for p in copy.rglob('*') if p.is_file()}
    data={**old,'copy':str(copy),'manifest':manifest,'phase':'M5-C2-B-R1','base_plan':str(BASE),'base_plan_sha256':BASE_SHA,
          'caption_mode':'timed_queue','evidence_protocol':'incremental_owner_upload_v1','evidence_queue_max_bytes':8388608,
          'evidence_disk_max_bytes':167772160,'evidence_disk_soft_stop_bytes':134217728,'evidence_ack_seconds':5,
          'services_started':False,'human_authorization':'User authorized lab recorder/presentation repair and requested notification when ready for supervised repeat; no repeat executed during repair'}
    (out/'plan.json').write_text(json.dumps(data,indent=2),encoding='utf-8');verify(out/'plan.json');return data


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);a=p.parse_args();print(json.dumps({'files':len(prepare(a.out)['manifest'])}))

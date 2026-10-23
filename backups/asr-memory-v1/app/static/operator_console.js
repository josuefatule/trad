(function (root) {
  "use strict";
  const phases = {waiting:"IDLE",connecting:"STARTING",live:"LIVE",draining:"STOPPING",
    stopped:"STOPPED",disconnected:"ERROR",error:"ERROR"};
  function actions(phase, {authorized=false, canStart=false, ownsSession=false, hasSession=false, localActive=false}={}) {
    const transition = ["STARTING","STOPPING"].includes(phase);
    return {start:authorized && canStart && !transition && !localActive,
      stop:authorized && phase === "LIVE" && localActive,
      clear:authorized && !transition && (!hasSession || ownsSession)};
  }
  function stats(values, minimum=5) {
    values = values.filter(Number.isFinite).sort((a,b)=>a-b);
    if (values.length < minimum) return null;
    const n = values.length;
    return {count:n,median:n%2?values[(n-1)/2]:(values[n/2-1]+values[n/2])/2,p95:values[Math.ceil(.95*n)-1]};
  }
  function userError(error) {
    const name=error?.name, text=String(error?.message || error || "").toLowerCase();
    if (name === "NotAllowedError" || name === "SecurityError") return "Permiso de micrófono denegado. Permite el acceso en el navegador y vuelve a intentar.";
    if (["NotFoundError","NotReadableError","OverconstrainedError"].includes(name) || text.includes("micrófono")) return "Micrófono no disponible. Comprueba el dispositivo y vuelve a seleccionarlo.";
    if (/backend|milestone|incompatib|normaliz/.test(text)) return "Backend/frontend incompatibles. Detén la sesión, reinicia FastAPI y recarga la consola.";
    if (/401|403|autentic|credencial/.test(text)) return "DeepL sin credenciales válidas o autenticación rechazada. Revisa la configuración local.";
    if (/translation_timeout|timeout de traducción/.test(text)) return "Timeout de traducción; consulta el segmento fallido en diagnósticos.";
    if (/translation_queue_full|saturada/.test(text)) return "Cola de traducción saturada; consulta los segmentos fallidos en diagnósticos.";
    if (/ya hay|already active/.test(text)) return "Ya hay una sesión activa. Usa la consola que la inició.";
    if (/wlk.*idioma/.test(text)) return "WLK no confirmó el idioma. Usa el arranque bidireccional documentado con la sesión detenida.";
    if (/wlk|websocket|conexión|timeout/.test(text)) return "WLK o conexión de sesión no disponible. Comprueba los servidores antes de volver a iniciar.";
    return "No se pudo completar la operación. Consulta los logs locales y vuelve a intentar cuando se resuelva el error.";
  }
  const ms = value => Number.isFinite(value)?`${Math.round(value)} ms`:"—";
  class ConsoleView {
    constructor(get) {
      this.get=get;this.phase="IDLE";this.authorized=false;this.localActive=false;this.snapshot=null;
      this.alertSince=new Map();this.startedAt=null;this.stopped=false;this.clearBusy=false;
      this.captureMode=typeof location!=="undefined" && location.pathname==="/capture";
      this.historyCursor=0;
      this.directionId="en-es";this.directionSupported=false;
      this.startPending=false;
      this.render();this.ready=this.initialize();
    }
    canSelectDirection() {
      return this.directionSupported && this.authorized && !this.localActive &&
        ["IDLE","STOPPED","ERROR"].includes(this.phase) && this.snapshot?.can_change_direction===true;
    }
    directionLabels() {
      const english=this.directionId==="en-es", source=english?"EN":"ES", target=english?"ESPAÑOL":"ENGLISH";
      this.get("direction").value=this.directionId;
      this.get("translation-label").textContent=target;
      this.get("translation-segments-label").textContent=`${target} SEGMENTS · sequence / segment ID`;
      this.get("normalized-label").textContent=`NORMALIZED ${source}`;
      this.get("raw-label").textContent=`RAW ${source} / ASR CONFIRMED`;
      this.get("normalization-info").textContent=english?"English: identity (no glossary)":"Spanish terminology glossary";
      this.get("direction-info").textContent=this.directionSupported?
        `${english?"English → Español":"Español → English"} · ${this.canSelectDirection()?"editable con sesión detenida":"idiomas bloqueados"}`:
        "Backend sin selección por sesión; modo histórico";
    }
    render() {
      const s=this.snapshot;
      const allowed=actions(this.phase,{authorized:this.authorized,canStart:s?.can_start ?? true,
        ownsSession:s?.owns_session,hasSession:!!s?.session_id,localActive:this.localActive});
      this.get("start").disabled=!allowed.start;this.get("stop").disabled=!allowed.stop;
      this.get("clear").disabled=!allowed.clear || this.clearBusy;
      this.get("refresh").disabled=this.localActive;this.get("microphone").disabled=this.localActive;
      this.get("direction").disabled=!this.canSelectDirection();
      this.get("acknowledge-stop").disabled=!(this.authorized && s?.owns_session && s?.requires_stop_acknowledgement);
      this.directionLabels();
      this.get("session-state").textContent=this.phase;
      if (this.get("session-state").dataset) this.get("session-state").dataset.state=this.phase;
    }
    phaseTo(phase) { this.phase=phase;this.render(); }
    error(error) {this.get("error").textContent=userError(error);}
    async initialize() {
      try {
        let stored=null;
        if(!this.captureMode)try{stored=JSON.parse(sessionStorage.getItem("operator-recovery"));}catch{}
        let response;
        if(stored?.token && stored?.secret)response=await fetch("/api/operator/resume",{method:"POST",
          headers:{"Content-Type":"application/json","X-Operator-Token":stored.token},body:JSON.stringify({resume_secret:stored.secret})});
        if(!response?.ok)response=await fetch("/api/operator/bootstrap",{cache:"no-store"});
        if(!response.ok) throw Error("Backend incompatible");
        const data=await response.json();
        if(data.protocol_version!==1 || data.capabilities?.operator_console!==1 || data.capabilities?.captions_clear!==1)
          throw Error("Backend incompatible");
        this.token=data.control_token;this.config=data.diagnostics_config;this.authorized=true;
        this.recovery=data.capabilities?.operator_recovery===1;this.serverPid=data.server_pid;
        this.directionSupported=data.capabilities?.session_direction===1;
        this.directionId=this.directionSupported?(data.default_direction || "en-es"):"es-en";
        if(!this.captureMode && this.recovery)try{sessionStorage.setItem("operator-recovery",JSON.stringify({token:this.token,secret:data.resume_secret}));}catch{}
        if(this.captureMode){this.render();return true;}
        await this.refresh();this.render();return this.authorized;
      }catch(error){this.error(error);this.phaseTo("ERROR");return false;}
    }
    async refresh() {
      if(!this.authorized) return;
      try {
        const response=await fetch(`/api/operator/status?after_event=${this.historyCursor}`,{cache:"no-store",headers:{"X-Operator-Token":this.token}});
        if([401,403].includes(response.status)){
          this.authorized=false;this.localActive=false;this.phaseTo("ERROR");
          this.get("error").textContent="Esta consola perdió autorización. Recarga para revisar la propiedad de la sesión.";return;
        }
        if(!response.ok) throw Error("Backend incompatible");
        const data=await response.json();
        if(data.protocol_version!==1) throw Error("Backend incompatible");
        this.snapshot=data;
        if(this.startPending && data.session_id && data.session_id!==this.pendingSessionId)this.startPending=false;
        if(data.direction && !this.startPending && (data.session_open || ["connecting","live","draining"].includes(data.state) || data.requires_stop_acknowledgement))
          this.directionId=data.direction.id;
        if(this.recovery && !this.captureMode) {
          this.localActive=this.startPending || (!!data.owns_session && ["connecting","live","draining"].includes(data.state));
          this.startedAt=data.reliability?.duration_seconds!=null?Date.now()-data.reliability.duration_seconds*1000:null;
          const frames=data.reliability?.audio_frames || 0, age=data.reliability?.audio_age_seconds;
          this.get("capture").textContent=this.localActive?`CAPTURE independiente · ${frames} frames PCM recibidos · última recepción ${age==null?"sin medir":age+" s"}`:"Micrófono inactivo";
          this.get("selected-microphone").textContent=this.localActive?"CAPTURE · consulta dispositivo en su ventana":
            (this.get("microphone").selectedOptions?.[0]?.textContent || "Predeterminado");
          if(this.consumeHistory)this.consumeHistory(data);
          if(data.owns_session)this.get("connection").textContent=data.state==="live"?"Connected · capture window":data.state;
        }
        if(!this.localActive && ["live","draining"].includes(data.state))
          this.get("connection").textContent="Connected · active session in another tab";
        if(!this.startPending && (this.recovery || !this.localActive) && !(this.phase==="ERROR" && this.get("error").textContent && !this.recovery)) this.phase=phases[data.state] || "ERROR";
        this.get("overlay-clients").textContent=`Overlay clients: ${data.overlay_connections}`;
        this.get("overlay-info").textContent=`${data.caption_config.mode} · requested ${data.caption_config.max_lines} lines · published sequence ${data.sequence} · visual generation ${data.visual_generation}`;
        this.get("last-caption").textContent=data.last_caption?`#${data.last_caption.sequence} · ${data.last_caption.text}`:"No caption in overlay window";
        if(this.recovery || !this.localActive) this.translator(data.translator, data.translator_verified);
        this.diagnostics(data);this.render();
        this.operational(data);
      }catch(error){this.get("overlay-clients").textContent="Overlay clients: —";this.get("overlay-diagnostics").textContent="Backend unavailable or incompatible. Not measured.";this.error(error);
        if(this.recovery){this.get("connection").textContent="FastAPI disconnected · capture not verified";this.phaseTo("ERROR");}
        if(!this.localActive){this.authorized=false;this.phaseTo("ERROR");}}
    }
    operational(data) {
      const h=data.reliability;if(!h)return;
      const labels={audio_frames_missing:"Micrófono sin flujo de audio: revisa la ventana de captura.",
        asr_messages_missing:"Hay señal de audio pero WLK no envía mensajes: revisa WLK.",
        operator_owner_missing:"Propietario ausente: recuperación administrativa disponible.",
        overlay_no_subscribers:"Sin clientes de overlay conectados; revisa OBS.",
        translator_degraded:"Traductor degradado: hay segmentos sin traducir.",translator_error:"Traductor detenido: revisa cuota/credenciales.",
        translator_recovering:"Traductor reintentando con espera limitada.",wlk_startup_backoff:"Reconectando con WLK antes de capturar audio.",
        capture_disconnected:"Captura desconectada; sesión incompleta. Se requiere un nuevo START.",
        session_transport_error:"Conexión de sesión perdida; sesión incompleta.",stop_timeout:"STOP agotó su plazo; contenido pendiente incompleto."};
      labels.resource_budget_exhausted="Límite de recursos excedido: sesión incompleta. Revisa el evento budget_exhausted en el log local.";
      const notices=String(h.reason || "").split(",").map(reason=>labels[reason]).filter(Boolean);
      if(h.outcome==="incomplete")notices.push("Finalización INCOMPLETA. Consulta los contadores de contenido pendiente/fallido.");
      if(h.stop_reason==="session_resource_budget")notices.push("Límite operativo de sesión alcanzado: finalización controlada. Inicia una sesión nueva cuando termine STOP.");
      if(h.translator?.reason==="provider_quota")notices.push("Cuota DeepL agotada. Revisa el plan antes de rearmar el traductor.");
      if(h.translator?.reason==="provider_auth")notices.push("DeepL rechazó credenciales. Corrige .env con la sesión detenida y reinicia FastAPI.");
      if(data.session_id && !data.owns_session)notices.push("Esta consola no es propietaria de la sesión; no tiene controles activos.");
      this.get("operational-alert").textContent=notices.join(" · ");
      this.get("reliability-diagnostics").textContent=JSON.stringify(h,null,2);
      this.get("recover-owner").disabled=data.owns_session || !data.session_id;
      this.get("rearm-translator").disabled=!data.owns_session;
      this.get("recovery-path").textContent=`Código local: .runtime/operator-${this.serverPid}.json (PID del servidor). Requiere propietario ausente ≥15 s.`;
    }
    async command(command,extra={}) {
      if(!this.authorized)return false;
      try{
        const response=await fetch(`/api/operator/${command}`,{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Token":this.token},
          body:JSON.stringify({session_id:this.snapshot?.session_id,...extra})});
        if(!response.ok){this.get("error").textContent="Control rechazado: verifica propiedad, sesión y requisitos de recuperación.";return false;}
        await this.refresh();return true;
      }catch{this.get("error").textContent="No se pudo contactar FastAPI; la operación no está confirmada. Verifica CAPTURE y el servidor.";return false;}
    }
    translator(status, verified=false) {
      const provider=status?.provider || "none", state=status?.state || "unknown";
      if(verified)this.verifiedProvider=provider;
      const label=state==="ready"?(provider===this.verifiedProvider?"Verified by result":"Configured; not verified"):
        ({disabled:"Disabled",misconfigured:"Misconfigured",unknown:"Not checked"}[state] || state);
      this.get("translator").textContent=`${provider === "mock"?"MOCK · ":""}${provider} · ${label}`;
      if(state==="misconfigured") this.get("error").textContent=provider==="deepl"?
        "DeepL sin credenciales o configuración incompleta. Revisa .env y reinicia FastAPI.":
        "Proveedor de traducción sin configurar. Revisa TRANSLATION_PROVIDER en .env y reinicia FastAPI.";
    }
    diagnostics(data) {
      const diagnostics=data.latency_diagnostics || {}, samples=diagnostics.backend_samples || [];
      const latest=samples.at(-1) || {};
      const observers=diagnostics.observers || [];
      const source=[...observers].filter(item=>item.sequence).sort((a,b)=>b.received_at-a.received_at)[0] || {};
      const metrics={asr_to_ready_ms:"ASR first appearance → READY",ready_to_normalized_ms:"READY → normalized",
        ready_to_translation_started_ms:"READY → translation started",provider_total_ms:"Provider total",
        translation_queue_delay_ms:"Translation queue delay",translation_to_hub_ms:"Translation completed → Hub"};
      const lines=[];
      for(const [key,label] of Object.entries(metrics)) {
        const summary=stats(samples.map(item=>item[key]),this.config.minimum_samples);
        lines.push(`${label}: latest ${ms(latest[key])}; median / p95 ${summary?`${ms(summary.median)} / ${ms(summary.p95)} (n=${summary.count})`:"— (insufficient samples)"}`);
      }
      const observerSamples=(diagnostics.observer_samples || []).filter(item=>item.observer_id===source.observer_id && item.render_measurement!=="DOM_clear");
      for(const [key,label] of Object.entries({renderer_delay_ms:"Overlay receive → DOM",paint_delay_ms:"Double-rAF paint estimate",
        hub_delivery_estimate_ms:"Hub delivery estimate",ready_to_visible_estimate_ms:"READY → visible estimate",
        asr_to_visible_estimate_ms:"ASR first appearance → visible estimate"})) {
        const summary=stats(observerSamples.map(item=>item[key]),this.config.minimum_samples);
        lines.push(`${label}: latest ${ms(source[key])}; median / p95 ${summary?`${ms(summary.median)} / ${ms(summary.p95)}`:"—"}`);
      }
      const alerts=[], now=Date.now();
      const check=(key,condition,label)=>{
        if(!condition || !["live","draining"].includes(data.state)){this.alertSince.delete(key);return;}
        if(!this.alertSince.has(key))this.alertSince.set(key,now);
        if(now-this.alertSince.get(key)>=this.config.sustained_seconds*1000)alerts.push(label);
      };
      check("queue",Number.isFinite(diagnostics.translation_queue_depth) && diagnostics.translation_queue_depth>=this.config.queue_depth_warning,"Cola de traducción acumulada");
      check("delay",diagnostics.translation_queue_depth>0 && latest.translation_queue_delay_ms>this.config.queue_delay_warning_ms,"Atraso de traducción sostenido");
      check("render",now/1000-source.received_at<3*this.config.poll_seconds && source.renderer_delay_ms>this.config.render_warning_ms,"Demora de renderer sostenida");
      this.get("latency-alert").textContent=alerts.join(" · ");
      lines.push(`Translation queue depth: ${diagnostics.translation_queue_depth ?? "—"}; subscribers: ${data.overlay_connections ?? "—"}`,
        `Display drops: ${data.display_drops ?? "—"}; reasons: ${JSON.stringify(data.display_drop_reasons || {})}`,
        `Broadcast errors: ${data.broadcast_errors ?? "—"}; filtered mocks: ${data.filtered_mock ?? "—"}`,
        `Backend sample #${latest.sequence ?? "—"}; observer sample #${source.sequence ?? "—"}; provider last attempt: ${ms(latest.provider_last_attempt_ms)}`,
        `Observer: ${source.observer_id ?? "—"}; uncertainty: ±${ms(source.delivery_uncertainty_ms)}`,
        `Visual queue: ${source.visual_queue_depth ?? "—"}; visible captions / lines: ${source.visible_caption_count ?? "—"} / ${source.visible_line_count ?? "—"}`,
        `Rolled-out lines: ${source.rolled_out_lines ?? "—"}; coalesced DOM updates: ${source.coalesced_render_updates ?? "—"}`,
        "Browser/OBS clients cannot be identified reliably. Estimates do not measure physical speech → OBS output.");
      this.get("overlay-diagnostics").textContent=lines.join("\n");
    }
    async clear() {
      if(this.get("clear").disabled || this.clearBusy)return;
      this.clearBusy=true;this.render();
      try {
        await this.refresh();const s=this.snapshot;
        if(!s)throw Error("Backend incompatible");
        const response=await fetch("/api/operator/clear",{method:"POST",headers:{"Content-Type":"application/json","X-Operator-Token":this.token},
          body:JSON.stringify({protocol_version:1,session_id:s.session_id,visual_generation:s.visual_generation})});
        if(!response.ok)throw Error("Conexión de control rechazada");
        const result=await response.json();
        if(result.protocol_version!==1)throw Error("Backend incompatible");
        this.get("control-notice").textContent=result.applied?"Overlay captions cleared. Audio and history continue.":"No active captions to clear.";
        await this.refresh();
      }catch(error){this.error(error);}finally{this.clearBusy=false;this.render();}
    }
  }
  const api={actions,stats,userError,ms,ConsoleView};root.OperatorConsole=api;
  if(typeof module!=="undefined")module.exports=api;
})(typeof window!=="undefined"?window:globalThis);

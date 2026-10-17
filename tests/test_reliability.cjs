// Real Operator scripts, isolated VM browser/media primitives. No real microphone.
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
module.exports=(async()=>{
  const origin='http://localhost:8010',saved=new Map();
  let tokenNumber=0,owner=null,state='waiting',sid=null,sourceCount=0,contextCount=0,trackStops=0,pcmSockets=[],resumeCount=0;
  const credentials=new Map(),windows=[],frames=[];
  const diagnostic={minimum_samples:5,poll_seconds:2,sustained_seconds:6,queue_depth_warning:3,queue_delay_warning_ms:1000,render_warning_ms:500};
  const caps={operator_console:1,captions_clear:1,operator_recovery:1,terminology_normalizer:1,translation_engine:1,caption_overlay:1,persistent_captions:1,caption_latency:1};
  const journal=[{journal_id:1,message:{type:'segmentation',session_id:'live',segmentation:{pending_segment:'',events:[],ready_segments:[{id:'live:1',text:'Texto.',word_count:1,reason:'punctuation',latency_ms:800}]},normalization:{segments:[{segment_id:'live:1',normalized_text:'Texto.',corrections:[],suggestions:[]}]}}},
    {journal_id:2,message:{type:'translation',session_id:'live',translation:{sequence:1,segment_id:'live:1',provider:'test',success:true,translated_text:'Text.'}}}];
  function bootstrap(){const token='token-'+(++tokenNumber),secret='secret-'+tokenNumber;credentials.set(token,secret);return {protocol_version:1,capabilities:caps,control_token:token,resume_secret:secret,diagnostics_config:diagnostic,server_pid:42};}
  const parentWindow={};
  let captureWindow=null;
  async function rig(capture=false){
    const nodes=new Map(),events=new Map();
    const get=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',value:'',dataset:{},replaceChildren(){},selectedOptions:[]});return nodes.get(id);};
    const win=capture?{opener:parentWindow,closed:false}:parentWindow;
    win.addEventListener=(type,fn)=>events.set(type,[...(events.get(type)||[]),fn]);
    const fire=async(type,event)=>{for(const fn of events.get(type)||[])await fn(event);};
    win.postMessage=async(data,target)=>{assert.equal(target,origin);await fire('message',{data,origin,source:capture?parentWindow:captureWindow});};
    win.open=()=>{captureWindow={closed:false,postMessage:(...args)=>captureWindow.real?.postMessage(...args)};windows.push(captureWindow);return captureWindow;};
    class Socket {
      static OPEN=1;
      constructor(url,protocols){assert.equal(protocols[1],owner=protocols[1]);sourceCount++;sid='live';state='live';this.readyState=1;this.bufferedAmount=0;pcmSockets.push(this);}
      send(data){frames.push(data);if(!data.byteLength)state='draining';}
      close(){this.readyState=3;this.onclose?.();}
    }
    class Worklet {constructor(){this.port={postMessage:()=>this.port.onmessage({data:{flushed:true}})};}disconnect(){}}
    class Worker {postMessage(message){if(message.command==='flush')this.onmessage({data:{flushed:true}});}terminate(){}}
    const track={label:'Simulated capture',stop(){trackStops++;}};
    const ctx=vm.createContext({window:win,document:{getElementById:get,body:{classList:{add(){}}}},
      location:{protocol:'http:',host:'localhost:8010',origin,pathname:capture?'/capture':'/operator',search:''},URLSearchParams,
      sessionStorage:{getItem:k=>saved.get(k),setItem:(k,v)=>saved.set(k,v)},Option:class{},setTimeout(){},clearTimeout(){},
      navigator:{mediaDevices:{enumerateDevices:async()=>[],getUserMedia:async()=>({getAudioTracks:()=>[track],getTracks:()=>[track]})}},
      AudioContext:class {constructor(){contextCount++;this.sampleRate=48000;this.state='running';this.audioWorklet={addModule:async()=>{}};}async resume(){}async close(){this.state='closed';}createMediaStreamSource(){return {connect(){},disconnect(){}};}},
      AudioWorkletNode:Worklet,Worker,WebSocket:Socket,
      fetch:async(url,options={})=>{
        const token=options.headers?.['X-Operator-Token'];let result;
        if(url.includes('bootstrap'))result=bootstrap();
        else if(url.includes('/resume')){
          assert.equal(JSON.parse(options.body).resume_secret,credentials.get(token));
          result=bootstrap();credentials.delete(token);if(owner===token)owner=result.control_token;resumeCount++;
        }else if(url.includes('/stop')){
          assert.equal(token,owner);
          await pcmSockets[0].onmessage({data:JSON.stringify({protocol_version:1,type:'operator_command',command:'stop',session_id:sid})});
          result={protocol_version:1,requested:true};
        }else result={protocol_version:1,session_id:sid,state,can_start:!['live','draining'].includes(state),owns_session:token===owner,
          overlay_connections:2,sequence:1,visual_generation:0,caption_config:{mode:'persistent_rolling',max_lines:3},translator:{state:'ready',provider:'test'},
          latency_diagnostics:{backend_samples:[],observers:[]},reliability:{state:'READY',reason:'audio_and_asr_observed',duration_seconds:5},
          operator_history:{cursor:2,first_translation_sequence:1,events:sid?journal:[],transcript:{partial_text:'',confirmed_text:'Texto.'},config:{},ui_history_segments:10}};
        return {ok:true,json:async()=>result};
      }});
    for(const name of ['operator_console.js','operator.js']){
      vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/',name),'utf8'),ctx);
      if(name==='operator_console.js')ctx.OperatorConsole=win.OperatorConsole;
    }
    await ctx.OperatorUI.ready;
    return {ctx,get,win,fire};
  }
  let parent=await rig();await parent.get('start').onclick();
  assert.equal(windows.length,1);assert.equal(contextCount,0); // Console never owns audio.
  const capture=await rig(true);captureWindow.real=capture.win;
  // Handshake may have fired before the test attached the popup's real window.
  await parent.fire('message',{source:captureWindow,origin,data:{type:'capture_ready'}});
  for(let i=0;i<20;i++)await Promise.resolve();
  assert.equal(contextCount,1);assert.equal(sourceCount,1);
  await pcmSockets[0].onmessage({data:JSON.stringify({type:'config',protocol_version:1,session_id:'live',capabilities:caps,translation_status:{state:'ready',provider:'test'}})});
  await parent.ctx.OperatorUI.refresh();
  assert.equal(parent.get('english').textContent,'Text.');
  assert.match(parent.get('capture').textContent,/CAPTURE independiente/);
  const stopsBefore=trackStops;
  await parent.fire('beforeunload');
  assert.equal(trackStops,stopsBefore);assert.equal(pcmSockets[0].readyState,1);
  parent=await rig();await parent.ctx.OperatorUI.refresh();
  assert.equal(resumeCount,1);assert.equal(contextCount,1);assert.equal(sourceCount,1);
  assert.equal(parent.get('english').textContent,'Text.');assert.equal(parent.get('normalized').textContent,'Texto.');
  assert.equal(parent.get('stop').disabled,false);assert.equal(parent.get('start').disabled,true);
  await parent.ctx.OperatorUI.refresh();assert.equal(parent.get('english').textContent,'Text.'); // Journal replay is idempotent.
  await parent.get('stop').onclick();assert.equal(frames.length,1);assert.equal(frames[0].byteLength,0);
  assert(trackStops>stopsBefore);assert.equal(parent.get('session-state').textContent,'STOPPING');
  parent.ctx.OperatorUI.consumeHistory({session_id:'live',operator_history:{history_gap:true,cursor:4,truncated_events:1,
    first_translation_sequence:1,events:[journal[1],{journal_id:4,message:{...journal[1].message,
      translation:{...journal[1].message.translation,sequence:3,translated_text:'Third.'}}}]}});
  assert.equal(parent.get('english').textContent,'Text. Third.');
  assert.match(parent.get('control-notice').textContent,/retirados/);
  // History truncation is explicit and leaves pipeline values untouched.
  const s={readyIds:new Set(),normalizedSegments:Array(600).fill('uno'),translatedSegments:Array(600).fill('one')};
  parent.ctx.boundHistory(s);assert.equal(s.normalizedSegments.length,10);assert(s.truncated>0);
  s.normalizedSegments=Array(4).fill('x'.repeat(50000));s.translatedSegments=['y'.repeat(90000)];
  parent.ctx.boundHistory(s);
  assert(s.normalizedSegments.join('').length<=60000);assert.equal(s.translatedSegments[0].length,60000);
  assert(s.truncatedCharacters>0);
  console.log('PASS: isolated capture, refresh/resume without audio restart, owner STOP/EOF, journal restore/dedup and visible UI bounds');
})();

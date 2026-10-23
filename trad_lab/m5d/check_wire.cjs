'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('node:assert/strict');
(async()=>{
  const copy=path.resolve(process.argv[2]),wire=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
  const assets=path.join(copy,'app/static');
  const nodes=new Map(['caption','caption-stage','overlay-canvas'].map(id=>[id,{
    textContent:'',hidden:true,style:{},classList:{add(){},remove(){}},
    set innerHTML(_){throw Error('Unsafe HTML');}
  }]));
  const sockets=[],listeners=new Map(),config={
    mode:'timed_queue',max_lines:3,font_size:48,max_width:1500,min_display_ms:1800,max_display_ms:6500,reading_wps:3,
    visual_queue_max:64,max_backlog_ms:20000,canvas_width:1920,canvas_height:1080,region_x:0,region_y:930,
    region_width:1920,region_height:150,padding_x:32,padding_y:8,line_height:1.2,position:'center',background_opacity:0
  };
  class Socket{
    static OPEN=1;
    constructor(url){assert.equal(url,'ws://192.168.50.10:3000/ws/overlay');this.readyState=1;sockets.push(this);}
    send(){} close(){this.readyState=3;}
  }
  const document={documentElement:{lang:'en'},getElementById:id=>nodes.get(id),
    createElement:()=>({getContext:()=>({measureText:text=>({width:text.length*12})})})};
  const context=vm.createContext({
    CaptionPresentation:require(path.join(assets,'caption_renderer.js')),
    OverlayGeometry:require(path.join(assets,'overlay_geometry.js')),
    OverlayClock:require(path.join(assets,'overlay_latency.js')).OverlayClock,
    document,location:{protocol:'http:',host:'192.168.50.10:3000',search:''},innerWidth:1920,innerHeight:1080,
    performance:{now:()=>100},requestAnimationFrame:fn=>fn(),
    window:{addEventListener:(event,fn)=>listeners.set(event,fn)},WebSocket:Socket,console,
    setTimeout:()=>1,clearTimeout(){},fetch:async url=>{assert.equal(url,'/api/overlay/config');return{ok:true,json:async()=>config};}
  });
  vm.runInContext(fs.readFileSync(path.join(assets,'overlay.js'),'utf8'),context);
  for(let i=0;i<10;i++)await Promise.resolve();
  let captions=0,clears=0;
  for(const message of wire){
    sockets[0].onmessage({data:JSON.stringify(message)});
    if(message.type==='caption'){
      assert.equal(nodes.get('caption').textContent.replace(/\n/g,' '),message.caption.text);captions++;
    }
    if(message.type==='captions_cleared'){
      assert.equal(nodes.get('caption').textContent,'');assert(nodes.get('caption').hidden);clears++;
    }
    if(message.type==='snapshot' && message.caption===null){assert.equal(nodes.get('caption').textContent,'');}
  }
  assert.equal(document.documentElement.lang,'es');assert(captions>=4);assert(clears>=4);
  assert.equal(nodes.get('caption-stage').style.top,'930px');
  assert.equal(nodes.get('caption').style.backgroundColor,'rgba(0, 0, 0, 0)');
  listeners.get('beforeunload')();assert.equal(sockets[0].readyState,3);
  console.log(JSON.stringify({status:'PASS',events:wire.length,exact_caption_DOM:captions,clear_DOM:clears,
    scope:'Actual TRAD->gateway memory wire through unchanged overlay.js/renderer, remote host, synthetic browser primitives'}));
})().catch(error=>{console.error(error);process.exitCode=1;});

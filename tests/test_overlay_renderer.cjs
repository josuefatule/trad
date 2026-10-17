const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {CaptionRenderer, splitCaption} = require('../app/static/caption_renderer.js');
const config = {mode: 'timed_queue', max_lines: 2, font_size: 48, max_width: 240, min_display_ms: 1800,
  max_display_ms: 6500, reading_wps: 3, visual_queue_max: 64, max_backlog_ms: 120000};
const measure = (text, size) => text.length * size / 4;

function rig(settings = {}) {
  let now = 0, id = 0;
  const timers = new Map(), visible = [], drops = [];
  const renderer = new CaptionRenderer({...config, ...settings}, {
    measure, now: () => now, show: frame => visible.push(frame), hide: () => visible.push(null),
    schedule: (fn, ms) => { timers.set(++id, {fn, at: now + ms}); return id; },
    cancel: id => timers.delete(id), report: (reason, count) => drops.push({reason, count}),
  });
  renderer.reset('a'); renderer.setState('live');
  return {renderer, visible, drops, timers, advance: ms => {
    const end = now + ms;
    while (true) {
      const next = [...timers.entries()].sort((a,b) => a[1].at - b[1].at)[0];
      if (!next || next[1].at > end) break;
      now = next[1].at; timers.delete(next[0]); next[1].fn();
    }
    now = end;
  }};
}
const caption = (text, sequence = 1, session_id = 'a') => ({text, sequence, session_id, provider: 'deepl'});

// Long text is paginated without losing or duplicating any word, punctuation or Unicode.
const text = 'Café naïve — This deliberately long English caption has enough words to wrap across many separate visual blocks while keeping every word intact.';
const split = splitCaption(text, config, measure);
assert(split.frames.length > 1);
assert.equal(split.frames.map(frame => frame.text).join(' ').replace(/\s+/g,' '), text);
for (const frame of split.frames) {
  assert(frame.text.split('\n').length <= 2);
  assert(frame.text.split('\n').every(line => measure(line, frame.fontSize) <= config.max_width));
}
const longToken = 'Electrocardiographically'.repeat(2);
const tokenFrames = splitCaption(longToken, config, measure).frames;
assert.equal(tokenFrames[0].text, longToken);
assert(tokenFrames[0].fontSize < 48);
for (let length=21; length<100; length++) {
  const mixed = splitCaption(`hello ${'a'.repeat(length)} world ${'b'.repeat(length)} end`, config, measure);
  for (const frame of mixed.frames) {
    assert(frame.text.split('\n').every(line => measure(line, frame.fontSize) <= config.max_width));
  }
}

const reading = rig();
reading.renderer.enqueue(caption(text)); reading.renderer.setState('stopped');
reading.advance(120000);
assert.equal(reading.visible.filter(Boolean).map(frame => frame.text).join(' ').replace(/\s+/g,' '), text);
assert.equal(reading.visible.at(-1), null);
assert.equal(reading.drops.length, 0);

const timer = rig();
timer.renderer.enqueue(caption('Hello.'));
timer.advance(1799); assert(timer.renderer.current);
timer.advance(1); assert.equal(timer.renderer.current, null);
const ceiling = rig({max_width:10000, max_display_ms:2500});
ceiling.renderer.enqueue(caption('read '.repeat(100)));
assert.equal(ceiling.renderer.current.duration,2500);
ceiling.advance(2500); assert.equal(ceiling.renderer.current,null);
timer.renderer.enqueue(caption('Hello.', 1)); assert.equal(timer.renderer.current, null);
timer.renderer.enqueue(caption('Stale', 2, 'old')); assert.equal(timer.renderer.current, null);
timer.renderer.enqueue({...caption('[MOCK EN] raw', 2), provider:'mock'}); assert.equal(timer.renderer.current, null);
timer.renderer.enqueue(caption('New caption', 3));
timer.renderer.reset('b'); timer.advance(10000);
assert.equal(timer.renderer.current, null); assert.equal(timer.renderer.seen, 0);

const reconnect = rig();
reconnect.renderer.enqueue(caption('Current', 1));
reconnect.renderer.setState('disconnected');
reconnect.renderer.setState('live'); reconnect.renderer.enqueue(caption('Current', 1));
assert.equal(reconnect.renderer.current, null); // reconnect never repeats an already accepted sequence
reconnect.renderer.enqueue(caption('Fresh', 2), 500);
reconnect.advance(500); assert.equal(reconnect.renderer.current, null);

const flood = rig({visual_queue_max: 2, max_backlog_ms: 4000});
for (let i=1; i<=12; i++) flood.renderer.enqueue(caption('A short caption.', i));
assert(flood.renderer.queue.length <= 2);
assert(flood.drops.some(drop => drop.reason === 'queue_overflow'));
flood.advance(30000); assert.equal(flood.renderer.current, null);
const excessive = rig(); excessive.renderer.enqueue(caption('x'.repeat(20001)));
assert.equal(excessive.drops[0].reason,'oversize');
const unreadable = rig(); unreadable.renderer.enqueue(caption('x'.repeat(1000)));
assert.equal(unreadable.drops[0].reason,'unreadable_token');

// Exercise actual transport and DOM assignments using controlled browser primitives.
module.exports = (async () => {
  const elements = new Map(['caption', 'caption-stage'].map(id => [id, {
    textContent: '', hidden:true, style:{}, classList:{add(){},remove(){}},
    set innerHTML(value) { throw new Error('Unsafe HTML assignment'); },
  }]));
  const sockets = [], callbacks = [];
  class Socket {
    static OPEN = 1;
    constructor() {this.readyState = 1; sockets.push(this);}
    close() {this.readyState = 3;}
    send(message) { (this.sent ||= []).push(JSON.parse(message)); }
  }
  const context = vm.createContext({
    CaptionPresentation: {CaptionRenderer},
    OverlayClock: require('../app/static/overlay_latency.js').OverlayClock,
    performance: {now: () => 0}, requestAnimationFrame: fn => fn(0),
    document: {getElementById: id => elements.get(id), createElement: () => ({
      getContext: () => ({font:'',measureText: text => ({width:measure(text,48)})}),
    })},
    fetch: async () => ({ok:true,json:async () => ({...config,position:'bottom',bottom_offset:70,background_opacity:.72})}),
    location:{protocol:'http:',host:'localhost:8010',search:''}, innerWidth:1920, innerHeight:1080,
    window:{addEventListener(){}}, WebSocket:Socket, console,
    setTimeout: fn => {callbacks.push(fn); return callbacks.length;}, clearTimeout(){},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../app/static/overlay.js'),'utf8'),context);
  // Initialization awaits fetch and JSON.
  for (let i=0;i<8;i++) await Promise.resolve();
  sockets[0].onopen();
  assert.equal(sockets[0].sent[0].type,'clock_probe');
  const send = data => sockets.at(-1).onmessage({data:JSON.stringify({protocol_version:2,...data})});
  send({type:'clock_sync',client_sent_ms:0,server_received_mono_ms:10000,server_sent_mono_ms:10000});
  send({type:'snapshot',event_id:0,session_id:'a',state:'live',server_time:0,caption:null});
  const literal = '<img src=x onerror=alert(1)>';
  send({type:'caption',event_id:1,session_id:'a',caption:{...caption(literal),
    published_mono_ms:10000,latency:{ready_to_hub_ms:900}}});
  assert.equal(elements.get('caption').textContent.replace(/\n/g,' '),literal);
  assert.equal(sockets[0].sent.at(-1).type,'render_sample');
  assert.equal(sockets[0].sent.at(-1).ready_to_visible_estimate_ms,900);
  assert.equal(elements.get('caption-stage').style.alignItems,'flex-end');
  send({type:'session',event_id:2,session_id:'b',state:'connecting'});
  assert.equal(elements.get('caption').textContent,'');
  send({type:'caption',event_id:3,session_id:'a',caption:caption('STALE',2)});
  assert.equal(elements.get('caption').textContent,'');
  sockets.at(-1).onclose(); assert(callbacks.length > 0);
  callbacks.at(-1)(); assert.equal(sockets.length,2);
  send({type:'snapshot',event_id:0,session_id:'b',state:'live',server_time:0,caption:null});
  send({type:'session',event_id:1,session_id:'b',state:'disconnected'});
  assert.equal(elements.get('caption').hidden,true);
  console.log('PASS: overlay pagination, timers, drops, reset, reconnect, stale events and safe DOM');
})();

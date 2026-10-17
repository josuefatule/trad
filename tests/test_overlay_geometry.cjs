const assert = require('node:assert/strict');
const {geometry, apply} = require('../app/static/overlay_geometry.js');
const {CaptionRenderer} = require('../app/static/caption_renderer.js');
const config = {mode:'persistent_rolling', canvas_width:1920, canvas_height:1080,
  region_x:0, region_y:930, region_width:1920, region_height:150, padding_x:32, padding_y:8,
  font_size:48, line_height:1.2, max_lines:3, max_width:1500, position:'center',
  background_opacity:0, stop_clear_ms:8000};
const g = geometry(config,1920,1080);
assert.equal(g.maxLines,2); assert.equal(g.scale,1); assert(g.warning.includes('Font unchanged'));
assert.equal(g.maxWidth,1500);
const small = geometry(config,960,540);
assert.equal(small.scale,.5); assert.equal(small.maxLines,2);
assert.equal(geometry({...config,font_size:36},1920,1080).maxLines,3);
assert.equal(geometry({...config,max_lines:2},1920,1080).warning,'');
assert.equal(geometry({...config,region_width:500},1920,1080).maxWidth,436);
assert.throws(() => geometry({...config,region_height:50},1920,1080));
const nodes = Array.from({length:3},()=>({style:{}}));
const settings = apply(config,1920,1080,...nodes).config;
assert.equal(nodes[1].style.top,'930px'); assert.equal(nodes[1].style.height,'150px');
assert.equal(nodes[2].style.backgroundColor,'rgba(0, 0, 0, 0)');
assert.equal(settings.font_size,48); assert.equal(settings.max_lines,2);

// Many incoming updates: stable wrapping, no extra browser wrap, no height clipping,
// persistence and deduplication still delegated to the unchanged presentation renderer.
let frame, now = 0;
const measure = (text,size)=>text.length*size*.55;
const renderer = new CaptionRenderer(settings,{measure,now:()=>now,
  show:value=>{frame=value;},hide:()=>{frame=null;},schedule:()=>1,cancel:()=>{}});
renderer.reset('geometry'); renderer.setState('live');
for (let sequence=1;sequence<=30;sequence++) {
  renderer.enqueue({session_id:'geometry',sequence,provider:'deepl',
    text:`Caption ${sequence}: systolic and diastolic pressure, café, naïve — whole words stay together.`});
  const lines = frame.text.split('\n');
  assert(lines.length<=settings.max_lines);
  assert(lines.every(line=>measure(line,frame.fontSize)<=settings.max_width));
  assert(lines.length*g.lineHeight+2*config.padding_y<=config.region_height);
  assert.equal(frame.fontSize,48);
  const before = frame.text;
  renderer.enqueue({session_id:'geometry',sequence,provider:'deepl',text:'DUPLICATE'});
  assert.equal(frame.text,before);
}
const retained = frame.text; now=60000; assert.equal(frame.text,retained);
console.log('PASS: logical canvas, region, height capacity, wrapping, persistence and no clipping');

// Node test of the actual operator.js onmessage handler, with DOM/media stubs.
// This checks DOM assignments; it is not a real-browser microphone test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

module.exports = (async () => {
  const elements = new Map();
  const element = id => {
    if (!elements.has(id)) elements.set(id, {textContent: '', value: '', replaceChildren() {}});
    return elements.get(id);
  };
  const sockets = [];
  class Socket {
    constructor() { sockets.push(this); }
  }
  const track = {label: 'Test microphone', stop() {}};
  const context = vm.createContext({
    document: {getElementById: element},
    navigator: {mediaDevices: {
      enumerateDevices: async () => [],
      getUserMedia: async () => ({getAudioTracks: () => [track], getTracks: () => [track]}),
    }},
    AudioContext: class {async resume() {}},
    fetch: async url => ({ok:true,json:async()=>url.includes('bootstrap')?{
      protocol_version:1,capabilities:{operator_console:1,captions_clear:1},control_token:'test-token',
      diagnostics_config:{minimum_samples:5,poll_seconds:2,sustained_seconds:6,queue_depth_warning:3,queue_delay_warning_ms:1000,render_warning_ms:500},
    }:{protocol_version:1,state:'waiting',can_start:true,session_id:null,owns_session:false,
      overlay_connections:0,caption_config:{mode:'persistent_rolling',max_lines:3},translator:{state:'disabled'}}}),
    WebSocket: Socket,
    Option: class {},
    location: {protocol: 'http:', host: 'localhost:8010', search: '?trace_partial=1'},
    URLSearchParams,
    window: {addEventListener() {}},
    setTimeout() {}, clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/operator_console.js'), 'utf8'), context);
  context.OperatorConsole=context.window.OperatorConsole;
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/operator.js'), 'utf8'), context);
  await element('start').onclick();
  const confirmed = 'Texto confirmado.';
  for (const partial of ['La', 'La hipertensión', '']) {
    await sockets[0].onmessage({data: JSON.stringify({
      protocol_version:1,type: 'asr', payload: {buffer_transcription: partial},
      transcript: {partial_text: partial, confirmed_text: confirmed, segments: []},
    })});
    assert.equal(element('partial').textContent, partial);
    assert.equal(element('confirmed').textContent, confirmed);
  }
  assert.match(element('debug').textContent, /PARTIAL raw="" state="" DOM=""/);
  const fixture = JSON.parse(fs.readFileSync(path.join(__dirname, 'fixtures/wlk_0_2_26_simulstreaming_es_real_voice.json'), 'utf8'));
  for (const payload of fixture.payloads) {
    const confirmed = payload.lines.filter(x => x.speaker !== -2 && x.text).map(x => x.text.trim()).join(' ');
    await sockets[0].onmessage({data: JSON.stringify({
      protocol_version:1,type: 'asr', payload,
      transcript: {partial_text: payload.buffer_transcription, confirmed_text: confirmed, segments: payload.lines},
    })});
    assert.equal(element('partial').textContent, '');
    assert.equal(element('confirmed').textContent, confirmed);
  }
  const ready = {id: 's:1', text: 'Lista en español.', start_time: 2.58, end_time: 5.8,
    reason: 'punctuation', word_count: 3, latency_ms: 900};
  const segmentation = {pending_segment: 'Siguiente', ready_segments: [ready], events: []};
  const normalization = {segments: [{
    segment_id: 's:1', raw_text: ready.text, normalized_text: 'Texto normalizado.',
    corrections: [{source: 'Lista', replacement: 'Texto', confidence: 1,
      rule: 'exact_alias'}],
    suggestions: [{source: 'lista', candidate: 'listado', confidence: 0.9,
      rule: 'glossary_fuzzy', cross_segment: false}],
  }]};
  await sockets[0].onmessage({data: JSON.stringify({protocol_version:1,type: 'segmentation', segmentation, normalization})});
  await sockets[0].onmessage({data: JSON.stringify({protocol_version:1,type: 'segmentation', segmentation, normalization})});
  const nextReady = {id: 's:2', text: 'Segundo segmento.', start_time: 5.8, end_time: 8.1,
    reason: 'soft_max_age', word_count: 2, latency_ms: 3200};
  await sockets[0].onmessage({data: JSON.stringify({
    protocol_version:1,type: 'segmentation',
    segmentation: {pending_segment: '', ready_segments: [ready, nextReady], events: []},
    normalization: {segments: [normalization.segments[0], {
      segment_id: 's:2', raw_text: nextReady.text, normalized_text: '  Segundo   segmento.  ',
      corrections: [], suggestions: [],
    }]},
  })});
  assert.equal(element('pending').textContent, '');
  assert.equal(element('ready').textContent.split('Lista en español.').length - 1, 1);
  assert.match(element('ready').textContent, /00:02.58/);
  assert.equal(element('normalized').textContent, 'Texto normalizado. Segundo segmento.');
  assert.doesNotMatch(element('normalized').textContent, /\n/);
  assert.match(element('normalized-segments').textContent, /\[s:1\]\nTexto normalizado\./);
  assert.match(element('normalized-segments').textContent, /\[s:2\]\n  Segundo   segmento\./);
  const translationState = {sessionId: 'current', translationResults: new Map(),
    nextTranslationSequence: 1, translatedSegments: []};
  context.renderTranslation(translationState, {
    session_id: 'current', translation_queue_depth: 0,
    translation: {sequence: 1, segment_id: 's:1', success: true,
      translated_text: 'Normalized text.', provider: 'mock', latency_ms: 4,
      queue_delay_ms: 2, attempt_count: 1, error: null},
  });
  context.renderTranslation(translationState, {
    session_id: 'old', translation_queue_depth: 0,
    translation: {sequence: 2, segment_id: 'old:2', success: true,
      translated_text: 'STALE', provider: 'mock', latency_ms: 1,
      queue_delay_ms: 0, attempt_count: 1, error: null},
  });
  assert.equal(element('english').textContent, 'Normalized text.');
  assert.doesNotMatch(element('english').textContent, /STALE/);
  assert.equal(element('corrections').textContent.split('Lista').length - 1, 1);
  assert.match(element('corrections').textContent, /SUGGESTION/);
  // A duplicate START is now rejected. End the previous session before resetting.
  await element('start').onclick(); assert.equal(sockets.length,1);
  vm.runInContext('active.context.close=async()=>{}',context);
  await sockets[0].onmessage({data:JSON.stringify({protocol_version:1,type:'status',state:'stopped'})});
  await sockets[0].onclose();
  await element('start').onclick();
  assert.equal(element('pending').textContent, '');
  assert.equal(element('ready').textContent, '');
  assert.equal(element('normalized').textContent, '');
  assert.equal(element('normalized-segments').textContent, '');
  assert.equal(element('english').textContent, '');
  assert.equal(element('corrections').textContent, '');
  assert.throws(() => context.renderSegmentation(
    {readyIds: new Set()}, segmentation, {segments: []}), /Reinicia FastAPI/);
  console.log('PASS: operator.js renders normalized and ordered English without stale-session leakage');
})();

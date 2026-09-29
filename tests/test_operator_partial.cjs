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
    WebSocket: Socket,
    Option: class {},
    location: {protocol: 'http:', host: 'localhost:8010', search: '?trace_partial=1'},
    URLSearchParams,
    window: {addEventListener() {}},
    setTimeout() {}, clearTimeout() {},
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/static/operator.js'), 'utf8'), context);
  await element('start').onclick();
  const confirmed = 'Texto confirmado.';
  for (const partial of ['La', 'La hipertensión', '']) {
    await sockets[0].onmessage({data: JSON.stringify({
      type: 'asr', payload: {buffer_transcription: partial},
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
      type: 'asr', payload,
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
  await sockets[0].onmessage({data: JSON.stringify({type: 'segmentation', segmentation, normalization})});
  await sockets[0].onmessage({data: JSON.stringify({type: 'segmentation', segmentation, normalization})});
  assert.equal(element('pending').textContent, 'Siguiente');
  assert.equal(element('ready').textContent.split('Lista en español.').length - 1, 1);
  assert.match(element('ready').textContent, /00:02.58/);
  assert.equal(element('normalized').textContent.split('Texto normalizado.').length - 1, 1);
  assert.equal(element('corrections').textContent.split('Lista').length - 1, 1);
  assert.match(element('corrections').textContent, /SUGGESTION/);
  await element('start').onclick();
  assert.equal(element('pending').textContent, '');
  assert.equal(element('ready').textContent, '');
  assert.equal(element('normalized').textContent, '');
  assert.equal(element('corrections').textContent, '');
  console.log('PASS: operator.js renders partial, RAW, NORMALIZED and audit data without duplicates');
})();

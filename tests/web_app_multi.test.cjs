const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
Object.defineProperty(globalThis, 'localStorage', {value: {getItem(){return null;}, setItem(){}}, configurable: true});
const I = require('../web/i18n.js');
const M = require('../web/multi_image.js');

// Browser integration without model calls: deferred FileReader is the real async boundary.
class Element {
  constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.attrs = {}; this.value = ''; this.textContent = ''; this.hidden = false; this.disabled = false; this.classList = {add(){}, remove(){}, toggle(){}}; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; this.textContent = ''; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; }
  toggleAttribute(k, present) { if (present) this.attrs[k] = ''; else delete this.attrs[k]; this.hidden = k === 'hidden' ? present : this.hidden; }
  addEventListener(k, f) { (this.listeners[k] ||= []).push(f); }
  fire(k, e) { return Promise.all((this.listeners[k] || []).map(f => f(e))); }
  closest() { return this; }
  get childElementCount() { return this.children.length; }
  scrollIntoView() {}
}
const content = el => el.textContent + el.children.map(content).join(' ');
const all = el => [el, ...el.children.flatMap(all)];
async function app(data = {runs: [], samples: [], records: {}, catalog: {A: {}, B: {}}}) {
  const elements = new Map(), pending = [];
  const el = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
  el('pipeline-select').value = 'sqlite'; el('engine-select').value = 'rapidocr'; el('multiview-input').checked = true;
  const document = {getElementById: el, createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag), addEventListener(){}};
  class Reader { readAsDataURL(file) { this.result = 'data:image/png;base64,' + file.name; pending.push(this); } }
  vm.runInNewContext(fs.readFileSync(require.resolve('../web/app.js'), 'utf8'), {
    window: {PartsI18n: {...I, apply(){}}, PartsMulti: M}, document, URL, URLSearchParams, setTimeout,
    Image: class {}, FileReader: Reader,
    fetch: async () => ({ok: true, json: async () => data}),
  });
  await new Promise(resolve => setImmediate(resolve));
  return {el, pending};
}

test('invalid drop during a pending valid selection cannot strand the uploader', async () => {
  const {el, pending} = await app();
  const file = {name: 'front.png', type: 'image/png', size: 100};
  const valid = el('upload-input').fire('change', {target: {files: [file]}});
  assert.equal(pending.length, 1);
  await el('upload-zone').fire('drop', {preventDefault(){}, dataTransfer: {files: [file, file, file, file]}});
  pending[0].onload(); await valid;
  assert.equal(el('predict-button').disabled, false);
  assert.match(el('upload-file-name').textContent, /front.png/);
});

test('photo navigation uses that photo identifier evidence rather than the first photo', async () => {
  const one = id => ({ocr_text: id, evidence: {views: [], conflicts: []}, id_hits: [[id, 1, id]],
    rankings: {shape: [id], sql: [id], image: [id], fused: [id]},
    retrieval: {keywords: [], candidates: [], pool: [], strong_ids: [id]},
    shape: {query: {available: false}, reference_scores: {}}, ms: {total: 1}});
  const first = one('A'), second = one('B');
  const fused = {...first, photos: [{index: 0, group: 0, duplicate_of: null, file: 'a.png', record: first}, {index: 1, group: 1, duplicate_of: null, file: 'b.png', record: second}], fusion: {weights: [1,1], support: {}}};
  const pair = {single: {top3: ['A'], top10: ['A'], elapsed_ms: 1}, multi: {top3: ['A'], top10: ['A'], elapsed_ms: 2}, photo_count: 2, independent_groups: 2};
  const {el} = await app({runs: [], samples: [], records: {}, catalog: {A: {}, B: {}}, multi_image_runs: [{scope: 'exploratory_same_object', visual_enabled: false, summary: {objects: 1, single: {n:1, top1_k:1, top3_k:1, recall10_k:1, latency_ms: {p50:1}}, multi: {n:1, top1_k:1, top3_k:1, recall10_k:1, latency_ms: {p50:2}}}, records: [{object_id: 'unit', gt:'A', record: fused, comparison: pair}]}]});
  await all(el('multi-experiments-body')).find(n => n.tagName === 'BUTTON').fire('click', {});
  await el('photo-strip').children[1].fire('click', {});
  assert.equal(el('ocr-text').textContent, 'B');
  assert.match(content(el('identifier-hits')), /B/);
  assert.doesNotMatch(content(el('identifier-hits')), /A/);
  assert.match(content(el('candidate-list')), /A/);
});

test('public replay shows source credit and a separately measured single-view output', async () => {
  const r = {ocr_text: 'RAW741CN', evidence: {views: [], conflicts: []}, id_hits: [],
    rankings: {shape: ['A'], sql: ['A'], image: ['A'], fused: ['A']},
    retrieval: {keywords: [], candidates: [], pool: [], strong_ids: []}, shape: {query: {available: false}}, ms: {total: 17}};
  const source = {page_url: 'https://commons.wikimedia.org/wiki/File:Photo.jpg', artist: 'Photographer', license: 'CC BY 2.0', capture_kind: 'video_frame', video_timecode: '00:00:22.800', quality_flags: ['blur']};
  const fused = {...r, photos: [0,1,2].map(index => ({index, group: index, duplicate_of: null, file: `p${index}.png`, source, record: r})), fusion: {weights: [1,1,1], support: {}}};
  const single = {...r, rankings: {...r.rankings, gated: ['B', 'A']}};
  const pair = {single: {top3: ['A'], top10: ['A'], elapsed_ms: 17}, multi: {top3: ['A'], top10: ['A'], elapsed_ms: 40}, photo_count: 3, independent_groups: 3};
  const {el} = await app({runs: [], samples: [], records: {}, catalog: {A: {}, B: {}}, multi_image_runs: [{scope: 'exploratory_same_object', visual_enabled: false,
    summary: {objects: 1, single: {n:1, top1_k:1, top3_k:1, recall10_k:1, latency_ms:{p50:17}}, multi: {n:1, top1_k:1, top3_k:1, recall10_k:1, latency_ms:{p50:40}}},
    records: [{object_id:'public',gt:'A',record:fused,comparison:pair,single_photo_records:[r,single,r]}]}]});
  await all(el('multi-experiments-body')).find(n => n.tagName === 'BUTTON').fire('click', {});
  await el('photo-strip').children[1].fire('click', {});
  assert.equal(el('source-link').href, source.page_url);
  assert.match(el('image-attribution').textContent, /Photographer.*CC BY 2.0/);
  assert.match(content(el('multi-photo-evidence')), /B/);
  assert.match(content(el('multi-photo-evidence')), /00:00:22.800/);
  assert.equal(el('ocr-text').textContent, 'RAW741CN');
});

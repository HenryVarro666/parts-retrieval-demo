const test = require('node:test');
const assert = require('node:assert/strict');
const M = require('../web/multi_image.js');

test('multi-file validation accepts a complete batch or rejects the third file', () => {
  const file = {name: 'a.png', size: 12, type: 'image/png'};
  assert.equal(M.fileError([file, file, file]), null);
  assert.equal(M.fileError([file, file, {...file, size: 11*1024*1024}]), 'error.large');
  assert.equal(M.fileError([file, file, file, file]), 'multi.tooMany');
  assert.equal(M.fileError([{...file, type: 'text/plain', name: 'x.txt'}]), 'error.invalidFile');
});

test('prediction body includes every photo and excludes local evaluation label', () => {
  const body = M.predictionPayload(['a', 'b', 'c'], {engine: 'rapidocr', multiview: true, pipeline: 'sqlite', verifyVisual: true, label: 'SECRET'});
  assert.deepEqual(body.images, ['a', 'b', 'c']);
  assert.equal(body.verify_visual, true);
  assert.equal(JSON.stringify(body).includes('SECRET'), false);
  assert.throws(() => M.predictionPayload(['a', 'b'], {pipeline: 'legacy'}));
});

test('photo selection returns corresponding geometry without changing fused rankings', () => {
  const record = {rankings: {shape: ['A']}, photos: [{record: {ocr_text: 'first', evidence: {selected_view: 'r0'}}}, {record: {ocr_text: 'second', evidence: {selected_view: 'r90'}}}]};
  assert.equal(M.photoRecord(record, 1).ocr_text, 'second');
  assert.equal(M.photoRecord(record, 0).evidence.selected_view, 'r0');
  assert.deepEqual(record.rankings.shape, ['A']);
});

test('optional label scores results after inference without treating agreement as correctness', () => {
  assert.deepEqual(M.score(['B', 'A', 'C'], 'A'), {top1: false, top3: true, recall10: true});
  assert.equal(M.score(['B'], ''), null);
  assert.deepEqual(M.score([], 'A'), {top1: false, top3: false, recall10: false});
});

test('saved selective verification is distinguished from forced verification', () => {
  assert.equal(M.runType({scope: 'exploratory_same_object', visual_enabled: true, force_visual: false}), 'multi.selectiveRun');
  assert.equal(M.runType({scope: 'confirmed_same_object', visual_enabled: true, force_visual: true}), 'multi.visualRun');
});

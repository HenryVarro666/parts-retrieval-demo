const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const modulePath = path.resolve(__dirname, '../web/i18n.js');

function fresh(storage) {
  delete require.cache[modulePath];
  if (storage) global.localStorage = storage;
  else delete global.localStorage;
  return require(modulePath);
}

test('unsupported or absent saved language defaults to Chinese', () => {
  const i18n = fresh({ getItem: () => 'fr', setItem() {} });
  assert.equal(i18n.language(), 'zh');
  assert.equal(i18n.t('page.title'), '元件识别工作台');
  i18n.setLanguage('en-US');
  assert.equal(i18n.language(), 'en');
  assert.equal(i18n.t('page.title'), 'Component Identification Workbench');
});

test('Spanish selection survives reload and switches dynamic messages', () => {
  const memory = new Map();
  const storage = { getItem: key => memory.get(key), setItem: (key, value) => memory.set(key, value) };
  let i18n = fresh(storage);
  i18n.setLanguage('es-MX');
  assert.equal(i18n.t('metrics.scope', { photos: 44, classes: 18 }), '44 fotos / 18 tipos');
  i18n = fresh(storage);
  assert.equal(i18n.language(), 'es');
  assert.equal(i18n.t('state.regression'), 'Empeora');
  assert.equal(i18n.t('run.sqlite_vlm'), 'SQLite · Verificación visual de nuevos candidatos');
});

test('storage being blocked does not stop switching languages', () => {
  const i18n = fresh({ getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } });
  assert.equal(i18n.language(), 'zh');
  assert.doesNotThrow(() => i18n.setLanguage('es'));
  assert.equal(i18n.language(), 'es');
});

test('UI localization preserves unknown source text and interpolated OCR exactly', () => {
  const i18n = fresh();
  i18n.setLanguage('en');
  const raw = 'NE555N <img src=x> $& {model} 8809VL';
  assert.equal(i18n.localize(raw), raw);
  assert.equal(i18n.t('vlm.observed', { text: raw }), `Visible text: ${raw}`);
  assert.equal(i18n.t('unknown.future.key'), 'unknown.future.key');
});

test('live shape failures use the exact backend messages and localize into Spanish', () => {
  const i18n = fresh();
  i18n.setLanguage('es');
  for (const [source, expected] of [
    ['Image could not be read or oriented.', 'No se pudo leer u orientar la imagen.'],
    ['Image is too small for foreground geometry.', 'La imagen es demasiado pequeña para estimar la forma.'],
    ['No sufficiently large foreground was separated from the background.', 'No se separó del fondo un primer plano de tamaño suficiente.'],
    ['Foreground touches the image edge and may be clipped.', 'El primer plano toca el borde; el objeto podría estar recortado.'],
    ['Foreground contour is degenerate.', 'El contorno del primer plano no permite estimar la forma.']
  ]) assert.equal(i18n.localize(source), expected);
});

test('every UI message has all three languages and the same interpolation fields', () => {
  const i18n = fresh();
  const fields = value => [...value.matchAll(/\{(\w+)\}/g)].map(m => m[1]).sort();
  for (const [key, values] of Object.entries(i18n.messages)) {
    assert.equal(values.length, 3, key);
    for (const value of values) assert.ok(typeof value === 'string' && value.length, key);
    assert.deepEqual(fields(values[0]), fields(values[1]), key);
    assert.deepEqual(fields(values[0]), fields(values[2]), key);
  }
});

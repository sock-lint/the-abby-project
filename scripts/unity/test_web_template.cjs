const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const template = fs.readFileSync(path.resolve(__dirname,
  '../../unity/AbbyCamp/Assets/WebGLTemplates/AbbyPhone/index.html'), 'utf8');
// Resolve Unity's standard single-data-file Web template directives. All
// filenames and runtime behavior below are synthetic; no browser account or
// network is involved.
const source = template.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/#if PROGRESSIVE_ASSET_LOADING[\s\S]*?#else([\s\S]*?)#endif/g, '$1')
  .replace(/#if SYMBOLS_FILENAME[\s\S]*?#endif/g, '')
  .replace(/#if USE_WASM\s*([\s\S]*?)#endif/g, '$1')
  .replace(/\{\{\{ JSON\.stringify\([A-Z_]+\) \}\}\}/g, '"Fixture Play"')
  .replace(/\{\{\{ [A-Z_]+ \}\}\}/g, 'fixture');

function loadPage(protocol = 'https:') {
  const elements = new Map();
  for (const [, id] of template.matchAll(/\bid="([^"]+)"/g)) {
    elements.set(id, {
      hidden: id === 'error', textContent: '', value: 0, focused: false,
      handlers: {},
      focus() { this.focused = true; },
      addEventListener(name, handler) { this.handlers[name] = handler; },
    });
  }
  const scripts = [];
  const instances = [];
  const viewportStyles = new Map();
  let reloads = 0;
  const window = {
    location: { protocol, reload() { reloads += 1; } },
    innerHeight: 852, addEventListener() {},
  };
  const document = {
    getElementById: id => elements.get(id),
    createElement: () => ({}),
    documentElement: { style: { setProperty: (key, value) => viewportStyles.set(key, value) } },
    body: { appendChild: script => scripts.push(script) },
  };
  vm.runInNewContext(source, {
    window, document, console: { error() {}, warn() {} },
    createUnityInstance(canvas, config, progress) {
      return new Promise((resolve, reject) => instances.push({ canvas, config, progress, resolve, reject }));
    },
  }, { filename: 'AbbyPhone/index.html' });
  return { elements, scripts, instances, viewportStyles, reloads: () => reloads };
}

test('opening Play starts loading without another user gesture and focuses the ready canvas', async () => {
  const page = loadPage();
  assert.equal(page.scripts.length, 1);
  assert.equal(page.elements.has('start'), false);
  assert.equal(page.elements.get('load-status').textContent, 'Loading Play...');
  page.scripts[0].onload();
  assert.equal(page.instances.length, 1);
  const runtime = page.instances[0];
  runtime.progress(0.5);
  assert.equal(page.elements.get('progress').value, 0.5);
  assert.match(page.elements.get('load-status').textContent, /50%/);
  runtime.resolve();
  await Promise.resolve();
  assert.equal(page.elements.get('welcome').hidden, true);
  assert.equal(page.elements.get('unity-canvas').focused, true);
});

test('a failed loader download exposes a keyboard-focused retry and reloads on retry', () => {
  const page = loadPage();
  page.scripts[0].onerror();
  assert.equal(page.instances.length, 0);
  assert.equal(page.elements.get('welcome').hidden, true);
  assert.equal(page.elements.get('error').hidden, false);
  assert.equal(page.elements.get('retry').focused, true);
  page.elements.get('retry').handlers.click();
  assert.equal(page.reloads(), 1);
});

test('runtime initialization failure preserves the error screen', async () => {
  const page = loadPage();
  page.scripts[0].onload();
  page.instances[0].reject(new Error('Synthetic initialization failure'));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(page.elements.get('error').hidden, false);
  assert.equal(page.elements.get('retry').focused, true);
});

test('an error banner during initialization cannot be hidden by later completion', async () => {
  const page = loadPage();
  page.scripts[0].onload();
  page.instances[0].config.showBanner('Synthetic WebGL error', 'error');
  page.instances[0].resolve();
  await Promise.resolve();
  assert.equal(page.elements.get('error').hidden, false);
  assert.equal(page.elements.get('unity-canvas').focused, false);
});

test('file URLs explain how to open Play without requesting a runtime', () => {
  const page = loadPage('file:');
  assert.equal(page.scripts.length, 0);
  assert.equal(page.elements.get('error').hidden, false);
  assert.equal(page.elements.get('error-message').textContent, 'Open Play through The Abby Project.');
});

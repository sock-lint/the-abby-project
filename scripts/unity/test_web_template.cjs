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

function loadPage(protocol = 'https:', options = {}) {
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
    innerHeight: 852, devicePixelRatio: options.devicePixelRatio,
    handlers: {},
    addEventListener(name, handler) { this.handlers[name] = handler; },
  };
  if (options.visualViewport) {
    window.visualViewport = {
      height: options.visualViewport.height, handlers: {},
      addEventListener(name, handler) { this.handlers[name] = handler; },
    };
  }
  const document = {
    getElementById: id => elements.get(id),
    createElement: () => ({}),
    documentElement: { style: { setProperty: (key, value) => viewportStyles.set(key, value) } },
    body: { appendChild: script => scripts.push(script) },
  };
  vm.runInNewContext(source, {
    window, document, console: { error() {}, warn() {} },
    createUnityInstance(canvas, config, progress) {
      // Match Unity's generated loader: config is copied by value into Module,
      // then Emscripten calls preRun with Module before player initialization.
      const Module = { ...config, canvas };
      return new Promise((resolve, reject) => {
        let started = false;
        const start = () => {
          if (started) return;
          started = true;
          for (const callback of Module.preRun || []) callback(Module);
        };
        instances.push({ canvas, config, Module, progress, start, reject,
          resolve() { start(); resolve({ Module }); },
        });
      });
    },
  }, { filename: 'AbbyPhone/index.html' });
  return { elements, scripts, instances, viewportStyles, window, reloads: () => reloads };
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

for (const [devicePixelRatio, expected] of [[1, 1], [1.25, 1.25], [2, 2], [3, 2]]) {
  test(`DPR ${devicePixelRatio} renders at ${expected}x without changing the CSS viewport`, () => {
    const page = loadPage('https:', { devicePixelRatio });
    page.scripts[0].onload();
    const runtime = page.instances[0];
    assert.equal(runtime.config.matchWebGLToCanvasSize, true);
    assert.equal(runtime.config.devicePixelRatio, expected);
    runtime.start();
    assert.equal(runtime.Module.devicePixelRatio, expected);
    assert.equal(page.viewportStyles.get('--viewport-height'), '852px');
    assert.equal(runtime.canvas, page.elements.get('unity-canvas'));
  });
}

test('missing, invalid and low DPR values retain a bounded 1x framebuffer', () => {
  for (const devicePixelRatio of [undefined, NaN, Infinity, -Infinity, 0, -1, 0.75, '2']) {
    const page = loadPage('https:', { devicePixelRatio });
    page.scripts[0].onload();
    assert.equal(page.instances[0].config.devicePixelRatio, 1);
  }
});

test('a DPR change before the loader download uses the latest display density', () => {
  const page = loadPage('https:', { devicePixelRatio: 1 });
  page.window.devicePixelRatio = 1.25;
  page.window.handlers.resize();
  page.scripts[0].onload();
  assert.equal(page.instances[0].Module.devicePixelRatio, 1.25);
});

test('a DPR change during initialization reaches the copied live Module before startup', () => {
  const page = loadPage('https:', { devicePixelRatio: 1 });
  page.scripts[0].onload();
  const runtime = page.instances[0];
  page.window.devicePixelRatio = 3;
  page.window.handlers.resize();
  assert.equal(runtime.Module.devicePixelRatio, 1);
  runtime.start();
  assert.equal(runtime.Module.devicePixelRatio, 2);
  assert.equal(page.instances.length, 1);
});

test('resizing the ready player follows fractional and capped DPR without reloading', async () => {
  const page = loadPage('https:', { devicePixelRatio: 2 });
  page.scripts[0].onload();
  const runtime = page.instances[0];
  runtime.resolve();
  await Promise.resolve();
  for (const [devicePixelRatio, expected] of [[1.25, 1.25], [3, 2], [1, 1]]) {
    page.window.devicePixelRatio = devicePixelRatio;
    page.window.handlers.resize();
    assert.equal(runtime.Module.devicePixelRatio, expected);
    assert.equal(page.viewportStyles.get('--viewport-height'), '852px');
  }
  assert.equal(page.instances.length, 1);
  assert.equal(page.scripts.length, 1);
  assert.equal(page.reloads(), 0);
});

test('visual viewport keyboard resizing keeps CSS height and capped live DPR in sync', () => {
  const page = loadPage('https:', {
    devicePixelRatio: 2, visualViewport: { height: 852 },
  });
  page.scripts[0].onload();
  const runtime = page.instances[0];
  runtime.start();
  page.window.visualViewport.height = 440;
  page.window.devicePixelRatio = 3;
  page.window.visualViewport.handlers.resize();
  assert.equal(page.viewportStyles.get('--viewport-height'), '440px');
  assert.equal(runtime.Module.devicePixelRatio, 2);
  assert.equal(page.reloads(), 0);
});

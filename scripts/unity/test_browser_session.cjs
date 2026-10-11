const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const pluginSource = fs.readFileSync(path.join(root,
  'unity/AbbyCamp/Assets/Plugins/WebGL/AbbyBrowserSession.jslib'), 'utf8');
const storageSource = fs.readFileSync(path.join(root,
  'frontend/src/constants/storage.js'), 'utf8');
const keys = vm.runInNewContext(storageSource.replace('export const ', 'const ')
  + '\nSTORAGE_KEYS;');

// Synthetic tokens only. No HTTP requests or access to a real browser profile.
const firstToken = 'a'.repeat(40);
const secondToken = 'b'.repeat(40);

function loadBridge(initial = {}, options = {}) {
  const values = new Map(Object.entries(initial));
  const removed = [];
  const navigations = [];
  const allocations = [];
  const heap = Buffer.alloc(8192);
  let nextAddress = 8;
  const storage = {
    getItem(key) {
      if (options.readError) throw new Error('Storage unavailable');
      return values.get(key) ?? null;
    },
    removeItem(key) {
      if (options.removeError) throw new Error('Storage unavailable');
      removed.push(key);
      values.delete(key);
    },
  };
  const window = {
    get localStorage() {
      if (options.accessError) throw new Error('Storage denied');
      return storage;
    },
    location: { assign: (target) => {
      if (options.navigationError) throw new Error('Navigation unavailable');
      navigations.push(target);
    } },
  };
  function allocate(size) {
    const address = nextAddress;
    nextAddress += size;
    allocations.push({ address, size });
    assert.ok(nextAddress < heap.length, 'Test heap has enough space');
    return address;
  }
  function writeString(value, address, size) {
    const bytes = Buffer.from(value, 'utf8');
    assert.ok(bytes.length < size, 'Allocation includes a null terminator');
    bytes.copy(heap, address);
    heap[address + bytes.length] = 0;
  }
  function readString(address) {
    return heap.toString('utf8', address, heap.indexOf(0, address));
  }
  const library = {};
  const context = vm.createContext({
    window,
    Module: { canvas: options.canvas },
    LibraryManager: { library },
    mergeInto: Object.assign,
    lengthBytesUTF8: (value) => Buffer.byteLength(value, 'utf8'),
    _malloc: allocate,
    stringToUTF8: writeString,
    UTF8ToString: readString,
  });
  const originalGlobals = Object.keys(context);
  vm.runInContext(pluginSource, context, { filename: 'AbbyBrowserSession.jslib' });
  return {
    library, values, removed, navigations, allocations,
    readToken: () => readString(library.AbbySession_ReadToken()),
    clearToken(expected) {
      if (expected === null) return library.AbbySession_ClearToken(0);
      const size = Buffer.byteLength(expected, 'utf8') + 1;
      const address = allocate(size);
      writeString(expected, address, size);
      library.AbbySession_ClearToken(address);
    },
    openDestination(target) {
      if (target === null) return library.AbbySession_OpenDestination(0);
      const size = Buffer.byteLength(target, 'utf8') + 1;
      const address = allocate(size);
      writeString(target, address, size);
      return library.AbbySession_OpenDestination(address);
    },
    checkNoGlobals: () => assert.deepEqual(Object.keys(context), originalGlobals),
  };
}

test('bridge uses the frontend token and cached-user keys', () => {
  assert.equal(keys.AUTH_TOKEN, 'abby_auth_token');
  assert.equal(keys.CACHED_USER, 'auth:last-user');
  const bridge = loadBridge({
    [keys.AUTH_TOKEN]: firstToken,
    [keys.CACHED_USER]: '{"id":123}',
  });
  assert.equal(bridge.readToken(), firstToken);
  bridge.clearToken(firstToken);
  assert.deepEqual(bridge.removed, [keys.AUTH_TOKEN, keys.CACHED_USER]);
});

test('display bridge converts framebuffer pixels into CSS units using the actual canvas', () => {
  const canvas = { width: 786, getBoundingClientRect: () => ({ width: 393 }) };
  const bridge = loadBridge({}, { canvas });
  assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 2);
  canvas.width = 491;
  assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 491 / 393);
  canvas.width = 393;
  assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 1);
  assert.deepEqual(bridge.allocations, []);
  assert.deepEqual(bridge.removed, []);
  bridge.checkNoGlobals();
});

test('display bridge follows resized CSS geometry even before the framebuffer catches up', () => {
  let cssWidth = 393;
  const canvas = { width: 786, getBoundingClientRect: () => ({ width: cssWidth }) };
  const bridge = loadBridge({}, { canvas });
  cssWidth = 844;
  assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 786 / 844);
  canvas.width = 1688;
  assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 2);
  bridge.checkNoGlobals();
});

test('a hidden, unavailable or invalid canvas falls back to a usable display scale', () => {
  for (const canvas of [undefined,
    { width: 786, getBoundingClientRect: () => ({ width: 0 }) },
    { width: 0, getBoundingClientRect: () => ({ width: 393 }) },
    { width: NaN, getBoundingClientRect: () => ({ width: 393 }) },
    { width: Infinity, getBoundingClientRect: () => ({ width: 393 }) },
    { width: 786, getBoundingClientRect: () => { throw new Error('Unavailable'); } },
  ]) {
    const bridge = loadBridge({}, { canvas });
    assert.equal(bridge.library.AbbyDisplay_GetPixelsPerCssPixel(), 1);
    assert.deepEqual(bridge.removed, []);
  }
});

test('missing token returns an allocated, null-terminated empty string', () => {
  const bridge = loadBridge();
  assert.equal(bridge.readToken(), '');
  assert.equal(bridge.allocations.length, 1);
  assert.equal(bridge.allocations[0].size, 1);
  assert.deepEqual(bridge.removed, []);
});

test('valid token is copied into a fresh malloc buffer on each read', () => {
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  assert.equal(bridge.readToken(), firstToken);
  assert.equal(bridge.readToken(), firstToken);
  assert.deepEqual(bridge.allocations.map(({ size }) => size), [41, 41]);
  assert.notEqual(bridge.allocations[0].address, bridge.allocations[1].address);
  assert.deepEqual(bridge.removed, []);
  bridge.checkNoGlobals();
});

test('malformed token values are rejected without mutating browser state', () => {
  const malformed = ['', 'a'.repeat(39), 'a'.repeat(41), 'g'.repeat(40),
    ` ${firstToken}`, `${firstToken}\n`, `Token ${firstToken}`, '{"token":"x"}'];
  for (const value of malformed) {
    const bridge = loadBridge({ [keys.AUTH_TOKEN]: value });
    assert.equal(bridge.readToken(), '');
    assert.deepEqual(bridge.removed, []);
    assert.equal(bridge.values.get(keys.AUTH_TOKEN), value);
  }
});

test('hexadecimal token shape allows uppercase letters', () => {
  const token = 'ABCDEF0123'.repeat(4);
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: token });
  assert.equal(bridge.readToken(), token);
});

test('inaccessible storage and read failures return an empty session', () => {
  for (const options of [{ accessError: true }, { readError: true }]) {
    const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken }, options);
    assert.equal(bridge.readToken(), '');
    assert.doesNotThrow(() => bridge.clearToken(firstToken));
    assert.deepEqual(bridge.removed, []);
  }
});

test('logout or account switching is visible on the next read', () => {
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  assert.equal(bridge.readToken(), firstToken);
  bridge.values.delete(keys.AUTH_TOKEN);
  assert.equal(bridge.readToken(), '');
  bridge.values.set(keys.AUTH_TOKEN, secondToken);
  assert.equal(bridge.readToken(), secondToken);
  bridge.checkNoGlobals();
});

test('clearing a matching rejected token removes only its auth state', () => {
  const bridge = loadBridge({
    [keys.AUTH_TOKEN]: firstToken,
    [keys.CACHED_USER]: '{"id":123}',
    'some-other-setting': 'preserved',
  });
  bridge.clearToken(firstToken);
  assert.equal(bridge.readToken(), '');
  assert.equal(bridge.values.has(keys.CACHED_USER), false);
  assert.equal(bridge.values.get('some-other-setting'), 'preserved');
  assert.deepEqual(bridge.removed, [keys.AUTH_TOKEN, keys.CACHED_USER]);
});

test('a late rejection cannot clear the session of a newly signed-in account', () => {
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  const rejected = bridge.readToken();
  bridge.values.set(keys.AUTH_TOKEN, secondToken);
  bridge.values.set(keys.CACHED_USER, '{"id":456}');
  bridge.clearToken(rejected);
  assert.equal(bridge.readToken(), secondToken);
  assert.equal(bridge.values.get(keys.CACHED_USER), '{"id":456}');
  assert.deepEqual(bridge.removed, []);
});

test('missing, malformed, or different expected token cannot clear cached identity', () => {
  for (const expected of [null, '', 'invalid', secondToken]) {
    const bridge = loadBridge({
      [keys.AUTH_TOKEN]: firstToken,
      [keys.CACHED_USER]: '{"id":123}',
    });
    bridge.clearToken(expected);
    assert.equal(bridge.readToken(), firstToken);
    assert.deepEqual(bridge.removed, []);
  }
  const bridge = loadBridge({ [keys.CACHED_USER]: '{"id":123}' });
  bridge.clearToken(firstToken);
  assert.deepEqual(bridge.removed, []);
  assert.equal(bridge.values.has(keys.CACHED_USER), true);
});

test('failed storage removal is best effort and does not escape to Unity', () => {
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken }, { removeError: true });
  assert.doesNotThrow(() => bridge.clearToken(firstToken));
  assert.deepEqual(bridge.removed, []);
});

test('journal navigation opens the existing journal tab without credentials', () => {
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  bridge.library.AbbySession_OpenJournal();
  assert.deepEqual(bridge.navigations, ['/chronicle?tab=journal']);
  assert.deepEqual(bridge.removed, []);
  bridge.checkNoGlobals();
});

test('every Unity typed destination is accepted by the same-origin bridge', () => {
  const clientSource = fs.readFileSync(path.join(root,
    'unity/AbbyCamp/Assets/AbbyCamp/Scripts/Services/AbbyApiClient.cs'), 'utf8');
  const targets = Array.from(clientSource.matchAll(/case PlayDestination\.\w+: return "([^"]+)";/g),
    (match) => match[1]);
  assert.equal(targets.length, 27, 'All approved destinations are covered');
  assert.equal(new Set(targets).size, targets.length);
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  for (const target of targets) assert.equal(bridge.openDestination(target), 1, target);
  assert.deepEqual(bridge.navigations, targets);
  assert.equal(bridge.values.get(keys.AUTH_TOKEN), firstToken);
  assert.deepEqual(bridge.removed, []);
  bridge.checkNoGlobals();
});

test('destination bridge rejects arbitrary URLs, credentials and unknown routes', () => {
  const rejected = [null, '', 'https://abby.example.com/', 'https://outside.example/',
    '//outside.example/', 'javascript:alert(1)', 'data:text/html,unsafe',
    '/\\outside.example/', '/api/auth/', '/manage', '/not-a-route',
    `/chronicle?tab=journal&token=${firstToken}`, '/chronicle?tab=unknown',
    '/chronicle?tab=journal#token', '/%2foutside.example',
    '/bestiary?tab=mounts&next=https://outside.example', ' /', '/\n'];
  const bridge = loadBridge({ [keys.AUTH_TOKEN]: firstToken });
  for (const target of rejected) assert.equal(bridge.openDestination(target), 0, String(target));
  assert.deepEqual(bridge.navigations, []);
  assert.equal(bridge.values.get(keys.AUTH_TOKEN), firstToken);
  assert.deepEqual(bridge.removed, []);
  bridge.checkNoGlobals();
});

test('destination navigation failures do not escape the WebGL bridge', () => {
  const bridge = loadBridge({}, { navigationError: true });
  assert.equal(bridge.openDestination('/'), 0);
  assert.deepEqual(bridge.navigations, []);
});

import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { elementalEvaluationPlugin, evaluationPrefix } from './elemental-evaluation-server.mjs';

const checkout = fileURLToPath(new URL('../..', import.meta.url));

test('private evaluation rejects relative roots, every checkout subtree and an unpinned manifest', async () => {
  await assert.rejects(elementalEvaluationPlugin({ root: './private' }), /must be absolute/);
  const inside = await mkdtemp(path.join(checkout, '.elemental-synthetic-check-'));
  const outside = await mkdtemp(path.join(os.tmpdir(), 'abby-elemental-synthetic-check-'));
  try {
    // Neither directory contains purchased art; these are deliberately invalid synthetic bytes.
    for (const root of [inside, outside]) await writeFile(path.join(root, 'manifest.json'), '{}');
    await assert.rejects(elementalEvaluationPlugin({ root: inside }), /outside the application checkout/);
    await assert.rejects(elementalEvaluationPlugin({ root: outside }), /manifest integrity failed/);
  } finally { await rm(inside, { recursive: true }); await rm(outside, { recursive: true }); }
});

test('unconfigured evaluation serves no private release and exposes only a loopback GET/HEAD module', async () => {
  const plugin = await elementalEvaluationPlugin({ root: null });
  assert.equal(plugin.apply, 'serve');
  let middleware;
  plugin.configureServer({ middlewares: { use(value) { middleware = value; } } });
  function request(url, method = 'GET', remoteAddress = '127.0.0.1') {
    const response = { statusCode: 200, headers: {}, setHeader(key, value) { this.headers[key] = value; }, end(body) { this.body = body; } };
    middleware({ url, method, socket: { remoteAddress } }, response, () => { response.next = true; });
    return response;
  }
  const module = request(`${evaluationPrefix}module.js`);
  assert.equal(module.body.toString(), 'export default null;');
  assert.equal(module.headers['Content-Type'], 'text/javascript');
  assert.equal(module.headers['Cache-Control'], 'no-store');
  assert.equal(module.headers['Content-Length'], Buffer.byteLength('export default null;'));
  assert.equal(request(`${evaluationPrefix}module.js`, 'HEAD').body, undefined);
  assert.equal(request(`${evaluationPrefix}module.js`, 'POST').statusCode, 405);
  assert.equal(request(`${evaluationPrefix}module.js`, 'GET', '192.0.2.5').statusCode, 403);
  for (const file of ['manifest.json', 'objects/unknown.glb', '../package.json', '..%2fpackage.json']) {
    assert.equal(request(`${evaluationPrefix}${file}`).statusCode, 404);
  }
  assert.equal(request('/unrelated').next, true);
});

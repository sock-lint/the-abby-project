import assert from 'node:assert/strict';
import { Buffer } from 'node:buffer';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { elementalEvaluationPlugin, evaluationPrefix, evaluationPin, evaluationPins, snakeCrabEvaluationPin } from './elemental-evaluation-server.mjs';

const checkout = fileURLToPath(new URL('../..', import.meta.url));

test('separate immutable pins preserve Bee/Bat review and allow only the exact verified Snake/Hermit Crab candidate', () => {
  assert.equal(evaluationPin.family_id, 'abby-elemental-bee-bat');
  assert.equal(evaluationPin.manifest_sha256, '7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5');
  assert.equal(snakeCrabEvaluationPin.family_id, 'abby-elemental-snake-hermit-crab');
  assert.equal(snakeCrabEvaluationPin.manifest_sha256, '2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3');
  assert.equal(evaluationPins.length, 2);
  assert.equal(evaluationPins[0], evaluationPin);
  for (const pin of evaluationPins) {
    assert.equal(pin.directory, `${pin.family_id}/${pin.release_version}/${pin.manifest_sha256}`);
    assert.ok(Object.isFrozen(pin));
  }
  assert.ok(Object.isFrozen(evaluationPins));
});

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

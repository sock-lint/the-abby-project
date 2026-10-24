// Private, opt-in browser evaluation only. This plugin is never loaded by the
// application Vite config and never stages purchased bytes in a source tree.
import { createHash } from 'node:crypto';
import { Buffer } from 'node:buffer';
import process from 'node:process';
import { readFile, realpath, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const evaluationPrefix = '/__abby_elemental_evaluation__/';
export const evaluationPin = Object.freeze({
  family_id: 'abby-elemental-bee-bat', release_version: '1.0.0',
  manifest_sha256: '7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5',
  directory: 'abby-elemental-bee-bat/1.0.0/7cce23a080a2a018fd5e4f55041c8f861df383ac857b94c543b3f331b13699e5',
});
export const snakeCrabEvaluationPin = Object.freeze({
  family_id: 'abby-elemental-snake-hermit-crab', release_version: '1.0.0',
  manifest_sha256: '2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3',
  directory: 'abby-elemental-snake-hermit-crab/1.0.0/2c14765c0fd379f4f06b76a8b38cb6be7a04f7e618d6eaff89c7cac84d1e80b3',
});
export const evaluationPins = Object.freeze([evaluationPin, snakeCrabEvaluationPin]);
const inventories = new Map([
  [evaluationPin.family_id, { files: 146, bytes: 31_484_079 }],
  [snakeCrabEvaluationPin.family_id, { files: 234, bytes: 88_597_843 }],
]);
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const within = (parent, child) => child === parent || child.startsWith(`${parent}${path.sep}`);

export async function elementalEvaluationPlugin({ root = process.env.ABBY_ELEMENTAL_EVALUATION_ROOT, applicationRoot = fileURLToPath(new URL('../..', import.meta.url)) } = {}) {
  const responses = new Map();
  let descriptor = null;
  if (root) {
    if (!path.isAbsolute(root)) throw new Error('Elemental evaluation root must be absolute.');
    const [releaseRoot, checkout] = await Promise.all([realpath(root), realpath(applicationRoot)]);
    if (within(checkout, releaseRoot)) throw new Error('Private elemental evaluation bytes must remain outside the application checkout.');
    const manifestBytes = await readFile(path.join(releaseRoot, 'manifest.json'));
    const pin = evaluationPins.find(({ manifest_sha256 }) => hash(manifestBytes) === manifest_sha256);
    if (!pin) throw new Error('Elemental evaluation manifest integrity failed.');
    const inventory = inventories.get(pin.family_id);
    const release = JSON.parse(manifestBytes.toString('utf8'));
    if (release.family_id !== pin.family_id || release.release_version !== pin.release_version
      || release.appearance_bindings?.schema_version !== 1 || release.files?.length !== inventory.files
      || release.files.reduce((sum, file) => sum + file.bytes, 0) !== inventory.bytes) throw new Error('Elemental evaluation release inventory mismatch.');
    const urls = {}, seen = new Set();
    for (const file of release.files) {
      if (!/^objects\/[a-f0-9]{64}\.(glb|png)$/.test(file.path) || seen.has(file.path)) throw new Error('Invalid elemental evaluation object path.');
      seen.add(file.path);
      const source = await realpath(path.join(releaseRoot, file.path));
      if (!within(releaseRoot, source) || !(await stat(source)).isFile()) throw new Error('Invalid elemental evaluation object source.');
      const bytes = await readFile(source);
      if (bytes.length !== file.bytes || hash(bytes) !== file.sha256) throw new Error(`Elemental evaluation object integrity failed: ${file.path}`);
      const url = `${evaluationPrefix}${file.path}`;
      responses.set(url, { bytes, type: file.media_type });
      urls[file.path] = url;
    }
    responses.set(`${evaluationPrefix}manifest.json`, { bytes: manifestBytes, type: 'application/json' });
    descriptor = { release, pin, urls, manifestUrl: `${evaluationPrefix}manifest.json` };
  }
  responses.set(`${evaluationPrefix}module.js`, { bytes: Buffer.from(`export default ${JSON.stringify(descriptor)};`), type: 'text/javascript' });
  return {
    name: 'abby-private-elemental-evaluation', apply: 'serve',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = request.url?.split('?')[0];
        if (!pathname?.startsWith(evaluationPrefix)) return next();
        if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(request.socket.remoteAddress)) { response.statusCode = 403; response.end(); return; }
        if (!['GET', 'HEAD'].includes(request.method)) { response.statusCode = 405; response.end(); return; }
        const entry = responses.get(pathname);
        response.setHeader('Cache-Control', 'no-store'); response.setHeader('X-Content-Type-Options', 'nosniff');
        if (!entry) { response.statusCode = 404; response.end(); return; }
        response.setHeader('Content-Type', entry.type); response.setHeader('Content-Length', entry.bytes.length);
        response.end(request.method === 'HEAD' ? undefined : entry.bytes);
      });
    },
  };
}

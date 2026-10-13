import { createHash } from 'node:crypto';
import { lstat, readFile, realpath } from 'node:fs/promises';
import { isAbsolute, join, resolve, dirname, relative } from 'node:path';

export const KIND = 'abby-private-asset-candidate';
export const REPOSITORY = 'sock-lint/the-abby-project';
export const RECIPE_PATH = 'content/rpg/asset-recipes/woodland.json';
export const FILES = ['bird-left.glb', 'bird-play.glb', 'bird-right.glb', 'bird.glb', 'chick-left.glb', 'chick-play.glb', 'chick-right.glb', 'chick.glb', 'manifest.json', 'woodland.glb'];
export const CHECKS = ['recipe', 'sourceIntegrity', 'candidateIntegrity', 'structure', 'materials', 'animation', 'grounding', 'render', 'mobile', 'loadErrors', 'networkIsolation'];
export const SCREENSHOTS = ['baseline-chick-portrait', 'candidate-chick-portrait', 'baseline-bird-portrait', 'candidate-bird-portrait', 'baseline-chick-landscape', 'candidate-chick-landscape'];
export const SHA = /^[a-f0-9]{64}$/;
export const COMMIT = /^[a-f0-9]{40}$/;
export function requireValue(value, code = 'INVALID_CONTRACT') { if (!value) throw new Error(code); }
export function keys(value, expected) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === expected.length && expected.every((key) => Object.hasOwn(value, key));
}
export function hash(value) { return createHash('sha256').update(value).digest('hex'); }
export function sourceDigest(files) {
  return hash(JSON.stringify(Object.fromEntries(FILES.map((name) => [name, files[name]]))));
}
export function recipe(value) {
  requireValue(keys(value, ['schemaVersion', 'target', 'operation', 'maxDimension'])
    && value.schemaVersion === 1 && value.target === 'woodland' && value.operation === 'woodland-texture-limit'
    && [128, 256, 384, 512].includes(value.maxDimension), 'INVALID_RECIPE');
  return value;
}
export async function noLinks(path) {
  requireValue(isAbsolute(path) && resolve(path) === path, 'INVALID_PATH');
  for (let current = path; ; current = dirname(current)) {
    try { requireValue(!(await lstat(current)).isSymbolicLink(), 'SYMLINK_REFUSED'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (dirname(current) === current) break;
  }
  return path;
}
export async function bytes(path, maximum = 64 * 1024 * 1024) {
  await noLinks(path);
  const stat = await lstat(path);
  requireValue(stat.isFile() && stat.nlink === 1 && stat.size > 0 && stat.size <= maximum, 'INVALID_FILE');
  const data = await readFile(path);
  const after = await lstat(path);
  requireValue(stat.dev === after.dev && stat.ino === after.ino && stat.size === after.size
    && stat.mtimeMs === after.mtimeMs && data.length === stat.size, 'FILE_CHANGED');
  return data;
}
export async function outsideGit(path) {
  await noLinks(path);
  for (let current = path; ; current = dirname(current)) {
    try { await lstat(join(current, '.git')); throw new Error('OUTPUT_INSIDE_GIT'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (dirname(current) === current) break;
  }
}
export async function verifyAssetCopy(directory, files) {
  for (const name of FILES) {
    const data = await bytes(join(directory, name));
    requireValue(data.length === files[name].bytes && hash(data) === files[name].sha256, 'ASSET_COPY_CHANGED');
  }
}
export async function workbench(path) {
  const raw = await bytes(path, 128 * 1024);
  const config = JSON.parse(raw);
  requireValue(keys(config, ['schemaVersion', 'baselineDirectory', 'files', 'blenderPath', 'blenderVersion'])
    && config.schemaVersion === 1 && config.blenderVersion === '4.1.1'
    && keys(config.files, FILES), 'INVALID_WORKBENCH');
  await noLinks(config.baselineDirectory);
  await noLinks(config.blenderPath);
  requireValue((await realpath(config.baselineDirectory)) === config.baselineDirectory, 'INVALID_WORKBENCH');
  requireValue((await lstat(config.blenderPath)).isFile(), 'INVALID_BLENDER');
  for (const name of FILES) {
    const record = config.files[name];
    requireValue(keys(record, ['sha256', 'bytes']) && SHA.test(record.sha256)
      && Number.isSafeInteger(record.bytes) && record.bytes > 0 && record.bytes <= 64 * 1024 * 1024, 'INVALID_CATALOG');
    const data = await bytes(join(config.baselineDirectory, name));
    requireValue(data.length === record.bytes && hash(data) === record.sha256, 'SOURCE_CHANGED');
  }
  const manifest = JSON.parse(await bytes(join(config.baselineDirectory, 'manifest.json'), 128 * 1024));
  requireValue(manifest.schema_version === 1 && manifest.delivery_review === 'private_evaluation'
    && keys(manifest.models, ['chick', 'bird', 'woodland']), 'INVALID_MANIFEST');
  for (const key of ['chick', 'bird', 'woodland']) {
    const model = manifest.models[key];
    requireValue(model.file === key + '.glb' && model.sha256 === config.files[model.file].sha256, 'INVALID_MANIFEST');
    for (const [action, take] of Object.entries(model.interaction_clips || {})) {
      requireValue(['play', 'left', 'right'].includes(action) && take.file === key + '-' + action + '.glb'
        && take.sha256 === config.files[take.file].sha256, 'INVALID_MANIFEST');
    }
  }
  return { config, manifest, catalogSha256: hash(raw), sourceInputsSha256: sourceDigest(config.files),
    sourceManifestSha256: config.files['manifest.json'].sha256 };
}
export function png(data) {
  requireValue(data.length >= 24 && data.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
    && data.toString('ascii', 12, 16) === 'IHDR', 'INVALID_PNG');
  const width = data.readUInt32BE(16), height = data.readUInt32BE(20);
  requireValue(width > 0 && height > 0 && width <= 4096 && height <= 4096, 'INVALID_PNG');
  return { width, height };
}
export function validateReceipt(value) {
  requireValue(keys(value, ['schemaVersion', 'kind', 'status', 'scope', 'headCommit', 'baseCommit', 'sourceCommit', 'issue',
    'checkedAt', 'expiresAt', 'catalogSha256', 'recipeSha256', 'sourceManifestSha256', 'sourceInputsSha256',
    'candidateManifestSha256', 'toolVersions', 'checks', 'screenshots', 'failureCodes']), 'INVALID_RECEIPT');
  requireValue(value.schemaVersion === 1 && value.kind === KIND && value.status === 'passed' && value.scope === 'private_evaluation'
    && [value.headCommit, value.baseCommit, value.sourceCommit].every((v) => COMMIT.test(v))
    && Number.isSafeInteger(value.issue) && value.issue > 0, 'INVALID_RECEIPT');
  requireValue(['catalogSha256', 'recipeSha256', 'sourceManifestSha256', 'sourceInputsSha256', 'candidateManifestSha256']
    .every((key) => SHA.test(value[key])), 'INVALID_RECEIPT');
  const checked = Date.parse(value.checkedAt), expires = Date.parse(value.expiresAt);
  requireValue(Number.isFinite(checked) && Number.isFinite(expires) && checked <= Date.now() + 5000
    && expires > Date.now() && expires > checked && expires <= checked + 3600000, 'STALE_RECEIPT');
  requireValue(keys(value.toolVersions, ['node', 'blender', 'chromium']) && value.toolVersions.blender === '4.1.1'
    && Object.values(value.toolVersions).every((v) => typeof v === 'string' && /^[A-Za-z0-9 ._-]{1,80}$/.test(v)), 'INVALID_RECEIPT');
  requireValue(keys(value.checks, CHECKS) && CHECKS.every((key) => value.checks[key] === true)
    && Array.isArray(value.failureCodes) && value.failureCodes.length === 0, 'FAILED_CHECKS');
  requireValue(Array.isArray(value.screenshots) && value.screenshots.length === SCREENSHOTS.length
    && value.screenshots.every((item, index) => keys(item, ['name', 'path', 'sha256', 'width', 'height'])
      && item.name === SCREENSHOTS[index] && isAbsolute(item.path) && SHA.test(item.sha256)
      && Number.isSafeInteger(item.width) && item.width > 0 && Number.isSafeInteger(item.height) && item.height > 0), 'INVALID_SCREENSHOTS');
  return value;
}
export function contained(root, path) {
  const rel = relative(root, path);
  return rel.length > 0 && !rel.startsWith('..') && !isAbsolute(rel);
}

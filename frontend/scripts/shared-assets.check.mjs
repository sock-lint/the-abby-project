import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { importReleases, verifyImport, writePreparedRelease } from '@abby-assets/release-tools';
import { SHARED_ASSET_SECRET_NAMES, sharedAssetsEnvironment, sharedAssetsRequired } from './shared-assets-config.mjs';
import { importSharedAssets } from './shared-assets.mjs';
import { verifySupplementals } from './companion-supplementals.mjs';
import { verifyBuiltPayloads } from './verify-built-shared-assets.mjs';

const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');

test('finished builds retain exact pinned runtime JSON bytes alongside images and models', async (t) => {
  const output = await mkdtemp(join(tmpdir(), 'abby-built-shared-json-'));
  t.after(() => rm(output, { recursive: true, force: true }));
  const json = Buffer.from('{"synthetic":"runtime document"}\n');
  const image = Buffer.from('synthetic image');
  const files = [json, image].map((bytes) => ({ sha256: hash(bytes), bytes: bytes.length }));
  await writeFile(join(output, 'runtime-checked.json'), json);
  await writeFile(join(output, 'image-checked.png'), image);
  await verifyBuiltPayloads(output, files);
  await writeFile(join(output, 'runtime-checked.json'), '{"synthetic":"different bytes"}\n');
  await assert.rejects(verifyBuiltPayloads(output, files), /1 pinned file\(s\) missing/);
  await rm(join(output, 'runtime-checked.json'));
  await assert.rejects(verifyBuiltPayloads(output, files), /1 pinned file\(s\) missing/);
});

async function localImport(t) {
  const root = await mkdtemp(join(tmpdir(), 'abby-local-release-import-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const releaseRoot = join(root, 'releases'), destination = join(root, 'shared');
  const lock = join(root, 'assets.lock.json'), workspace = join(root, 'workspace');
  const supplementalDestination = join(root, 'supplemental');
  async function release(version) {
    const bytes = Buffer.from(JSON.stringify({ synthetic: version })), sha256 = hash(bytes), path = `objects/${sha256}.json`;
    const manifest = { schema_version: 1, kind: 'file-library', family_id: 'synthetic-local-import', release_version: version,
      label: 'Synthetic local import', files: [{ path, sha256, bytes: bytes.length, media_type: 'application/json' }],
      entries: [{ id: 'synthetic', runtime_path: 'synthetic.json', file: path, sha256, bytes: bytes.length, media_type: 'application/json' }] };
    const result = await writePreparedRelease({ workspace: root, output: releaseRoot, manifest, objects: new Map([[path, bytes]]) });
    return Object.fromEntries(['directory', 'family_id', 'manifest_sha256', 'release_version'].map((key) => [key, result[key]]));
  }
  const previous = await release('1.0.0'), current = await release('1.0.1');
  const writeLock = (pin) => writeFile(lock, JSON.stringify({ schema_version: 1, releases: [pin] }));
  await writeLock(previous);
  await importReleases({ lock, destination, releaseRoot });
  await writeLock(current);
  await mkdir(join(workspace, 'assets'), { recursive: true });
  const bytes = Buffer.from('synthetic supplemental portrait');
  const file = { path: 'assets/chick.png', filename: 'chick.png', bytes: bytes.length, sha256: hash(bytes) };
  await writeFile(join(workspace, file.path), bytes);
  const inventory = Buffer.from(JSON.stringify({ pin: current, files: [{ path: file.path, bytes: file.bytes, sha256: file.sha256 }] }));
  await writeFile(join(workspace, 'inventory.json'), inventory);
  const supplementalDefinition = { pin: current, index_sha256: 'b'.repeat(64), inventory_sha256: hash(inventory), files: [file] };
  return { root, lock, destination, supplementalDestination, supplementalDefinition, workspace, previous, writeLock,
    environment: { ABBY_ASSETS_RELEASE_ROOT: releaseRoot } };
}

async function tree(root) {
  try {
    const files = await readdir(root, { recursive: true, withFileTypes: true });
    const result = await Promise.all(files.filter((file) => file.isFile()).map(async (file) => {
      const path = join(file.parentPath, file.name);
      return [path.slice(root.length + 1), hash(await readFile(path))];
    }));
    return result.sort(([left], [right]) => left.localeCompare(right));
  } catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

test('a local release root without supplemental inputs fails before changing either installed tree', async (t) => {
  const data = await localImport(t), before = await tree(data.destination);
  let failure;
  await assert.rejects(importSharedAssets(data), (error) => { failure = error; return true; });
  assert.deepEqual(await tree(data.destination), before);
  assert.equal(await tree(data.supplementalDestination), null);
  assert.match(failure.message, /ABBY_COMPANION_WORKSPACE/);
});

test('invalid offline workspace bytes fail before changing either installed tree', async (t) => {
  const data = await localImport(t), before = await tree(data.destination);
  await writeFile(join(data.workspace, 'assets/chick.png'), 'changed');
  await assert.rejects(importSharedAssets({ ...data,
    environment: { ...data.environment, ABBY_COMPANION_WORKSPACE: data.workspace } }), /integrity mismatch/);
  assert.deepEqual(await tree(data.destination), before);
  assert.equal(await tree(data.supplementalDestination), null);
});

test('verified workspace preparation leaves portraits unstaged when the release import fails', async (t) => {
  const data = await localImport(t), before = await tree(data.destination);
  const { releases: [current] } = JSON.parse(await readFile(data.lock, 'utf8'));
  await writeFile(join(data.environment.ABBY_ASSETS_RELEASE_ROOT, current.directory, 'manifest.json'), '{}');
  await assert.rejects(importSharedAssets({ ...data,
    environment: { ...data.environment, ABBY_COMPANION_WORKSPACE: data.workspace } }), /manifest.*SHA-256/);
  assert.deepEqual(await tree(data.destination), before);
  assert.equal(await tree(data.supplementalDestination), null);
});

test('offline workspace imports verify both trees and a local rollback reuses only verified installed portraits', async (t) => {
  const data = await localImport(t);
  await rm(data.destination, { recursive: true });
  await importSharedAssets({ ...data, environment: { ...data.environment, ABBY_COMPANION_WORKSPACE: data.workspace } });
  await verifyImport(data);
  await verifySupplementals(data.supplementalDestination, data.supplementalDefinition);
  const portraits = await tree(data.supplementalDestination);
  await data.writeLock(data.previous);
  await importSharedAssets(data);
  await verifyImport(data);
  assert.deepEqual(await tree(data.supplementalDestination), portraits);
  await writeFile(join(data.supplementalDestination, 'chick.png'), 'changed installed portrait');
  const releaseBefore = await tree(data.destination), portraitsBefore = await tree(data.supplementalDestination);
  await assert.rejects(importSharedAssets(data), /ABBY_COMPANION_WORKSPACE/);
  assert.deepEqual(await tree(data.destination), releaseBefore);
  assert.deepEqual(await tree(data.supplementalDestination), portraitsBefore);
});

test('optional builds and an explicit requirement are distinct', () => {
  assert.equal(sharedAssetsRequired(undefined), false);
  assert.equal(sharedAssetsRequired('false'), false);
  assert.equal(sharedAssetsRequired('true'), true);
});

test('blank or malformed required build secrets fail instead of disabling the gate', () => {
  for (const value of ['', ' ', '\n', 'TRUE', '1', 'false ', null]) {
    assert.throws(() => sharedAssetsRequired(value), /must be true or false/);
  }
});

test('dedicated shared credentials override only the scoped process copy and discard stale profiles/tokens', () => {
  const environment = {
    AWS_ACCESS_KEY_ID: 'synthetic-old-media-key', AWS_SECRET_ACCESS_KEY: 'synthetic-old-media-secret',
    AWS_SESSION_TOKEN: 'synthetic-stale-token', AWS_PROFILE: 'old-media-profile', AWS_DEFAULT_PROFILE: 'old-default',
    ABBY_ASSETS_ACCESS_KEY_ID: 'synthetic-shared-reader', ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-shared-secret',
    UNRELATED_SETTING: 'preserved',
  };
  const result = sharedAssetsEnvironment(environment);
  assert.equal(result.AWS_ACCESS_KEY_ID, 'synthetic-shared-reader');
  assert.equal(result.AWS_SECRET_ACCESS_KEY, 'synthetic-shared-secret');
  for (const name of ['AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_DEFAULT_PROFILE']) assert.equal(result[name], undefined);
  assert.equal(result.UNRELATED_SETTING, 'preserved');
  assert.equal(environment.AWS_ACCESS_KEY_ID, 'synthetic-old-media-key');
  assert.equal(environment.AWS_PROFILE, 'old-media-profile');
  assert.equal(environment.AWS_SESSION_TOKEN, 'synthetic-stale-token');
});

test('local named profiles remain supported without dedicated credentials and explicit shared tokens are scoped', () => {
  const local = { AWS_PROFILE: 'abby-assets-abby-reader', AWS_SHARED_CREDENTIALS_FILE: '/synthetic/credentials' };
  assert.deepEqual(sharedAssetsEnvironment(local), local);
  const temporary = sharedAssetsEnvironment({ ...local, ABBY_ASSETS_ACCESS_KEY_ID: 'synthetic-key',
    ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-secret', ABBY_ASSETS_SESSION_TOKEN: 'synthetic-token' });
  assert.equal(temporary.AWS_SESSION_TOKEN, 'synthetic-token');
  assert.equal(temporary.AWS_PROFILE, undefined);
});

test('partial or blank dedicated credentials fail without disclosing any credential value', () => {
  for (const environment of [
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_SECRET_ACCESS_KEY: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_SESSION_TOKEN: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_ACCESS_KEY_ID: '', ABBY_ASSETS_SECRET_ACCESS_KEY: 'sensitive-synthetic-value' },
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value', ABBY_ASSETS_SECRET_ACCESS_KEY: '  ' },
    { ABBY_ASSETS_ACCESS_KEY_ID: 'sensitive-synthetic-value', ABBY_ASSETS_SECRET_ACCESS_KEY: 'synthetic-secret', ABBY_ASSETS_SESSION_TOKEN: '' },
  ]) {
    assert.throws(() => sharedAssetsEnvironment(environment), (error) => {
      assert.match(error.message, /ABBY_ASSETS_/);
      assert.ok(!error.message.includes('sensitive-synthetic-value'));
      return true;
    });
  }
});

test('shared mounts are distinct from legacy media credentials in the Docker build', async () => {
  assert.ok(!SHARED_ASSET_SECRET_NAMES.some((name) => name.startsWith('AWS_')));
  const dockerfile = await readFile(new URL('../../Dockerfile', import.meta.url), 'utf8');
  const shared = dockerfile.split('# Shared releases are pinned')[1].split('# Keep this RUN separate')[0];
  for (const name of ['ABBY_ASSETS_ACCESS_KEY_ID', 'ABBY_ASSETS_SECRET_ACCESS_KEY', 'ABBY_ASSETS_SESSION_TOKEN']) assert.ok(shared.includes(`id=${name}`));
  assert.ok(!shared.includes('id=AWS_ACCESS_KEY_ID'));
  assert.ok(!shared.includes('id=AWS_SECRET_ACCESS_KEY'));
  const legacy = dockerfile.split('# Shared releases are pinned')[0];
  assert.ok(legacy.includes('id=AWS_ACCESS_KEY_ID'));
  assert.ok(legacy.includes('id=AWS_SECRET_ACCESS_KEY'));
});

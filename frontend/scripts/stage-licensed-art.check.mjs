import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { Readable } from 'node:stream';
import test from 'node:test';
import { downloadArtifact, stageLicensedArt, validateBundle } from './stage-licensed-art.mjs';

const baseline = JSON.parse(await readFile(new URL('../src/storybook/presentation.json', import.meta.url), 'utf8'));
// A synthetic 1x1 PNG, never purchased artwork.
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cRZ8AAAAASUVORK5CYII=', 'base64');
const digest = (value) => createHash('sha256').update(value).digest('hex');
const config = {
  endpoint: 'https://synthetic-storage.invalid', bucket: 'synthetic-private', key: 'private/synthetic.json',
  region: 'us-east-1', accessKeyId: 'synthetic-access-key', secretAccessKey: 'synthetic-secret-key',
};

function makeBundle() {
  const presentation = structuredClone(baseline);
  Object.assign(presentation.companion, {
    label: 'Your chick', art_key: 'chick', temporary: false,
    portrait: 'chick.png', happy_portrait: 'chick.png', blink_portrait: 'chick.png',
  });
  const images = Object.fromEntries(['chick.png', 'fledgling.png', 'bird.png'].map((name) => [
    name, { sha256: digest(png), base64: png.toString('base64') },
  ]));
  return { schema_version: 1, presentation, images };
}

async function fixture(t) {
  const parent = resolve(tmpdir());
  const root = await mkdtemp(join(parent, 'abby-licensed-art-test-'));
  t.after(async () => {
    assert.equal(dirname(resolve(root)), parent);
    assert.ok(basename(root).startsWith('abby-licensed-art-test-'));
    await rm(root, { recursive: true, force: true });
  });
  const bytes = Buffer.from(JSON.stringify(makeBundle()));
  const releasePath = join(root, 'release.json');
  const baselinePath = join(root, 'baseline.json');
  await writeFile(releasePath, JSON.stringify({ key: config.key, sha256: digest(bytes) }));
  await writeFile(baselinePath, JSON.stringify(baseline));
  return {
    root, bytes,
    options: {
      secretPath: join(root, 'ABBY_MEADOW_ASSETS'), releasePath, baselinePath,
      destination: join(root, 'licensed'), expectedHash: digest(bytes), required: false,
      download: async (received) => { assert.deepEqual(received, config); return bytes; },
    },
  };
}

test('public checkout skips absent secrets without downloading or creating art', async (t) => {
  const { root, options } = await fixture(t);
  options.download = async () => assert.fail('A public build must not download private art');
  assert.deepEqual(await stageLicensedArt(options), { staged: false, imageCount: 0 });
  assert.ok(!(await readdir(root)).includes('licensed'));
});

test('production required flag refuses missing secret via ARG or Coolify secret', async (t) => {
  const { root, options } = await fixture(t);
  await assert.rejects(stageLicensedArt({ ...options, required: true }), /Required licensed asset build secret is missing/);
  await writeFile(join(root, 'ABBY_MEADOW_ASSETS_REQUIRED'), 'true\n');
  await assert.rejects(stageLicensedArt(options), /Required licensed asset build secret is missing/);
});

test('valid configuration secret stages only verified portraits and compatible presentation', async (t) => {
  const { options } = await fixture(t);
  await writeFile(options.secretPath, JSON.stringify(config));
  assert.deepEqual(await stageLicensedArt(options), { staged: true, imageCount: 3 });
  assert.deepEqual((await readdir(options.destination)).sort(), ['bird.png', 'chick.png', 'fledgling.png', 'presentation.json']);
  assert.deepEqual(await readFile(join(options.destination, 'chick.png')), png);
  const staged = JSON.parse(await readFile(join(options.destination, 'presentation.json'), 'utf8'));
  assert.equal(staged.companion.id, baseline.companion.id);
  assert.equal(staged.companion.temporary, false);
});

test('Coolify AWS secret files reuse existing credentials with committed release key and digest', async (t) => {
  const { root, options } = await fixture(t);
  const files = {
    AWS_S3_ENDPOINT_URL: config.endpoint, AWS_STORAGE_BUCKET_NAME: config.bucket,
    AWS_S3_REGION_NAME: config.region, AWS_ACCESS_KEY_ID: config.accessKeyId, AWS_SECRET_ACCESS_KEY: config.secretAccessKey,
  };
  for (const [name, value] of Object.entries(files)) await writeFile(join(root, name), value);
  await writeFile(join(root, 'ABBY_MEADOW_ASSETS_REQUIRED'), 'true');
  assert.deepEqual(await stageLicensedArt({ ...options, expectedHash: '' }), { staged: true, imageCount: 3 });
});

test('incomplete AWS configuration or invalid JSON fails even when art is optional', async (t) => {
  const { root, options } = await fixture(t);
  await writeFile(join(root, 'AWS_ACCESS_KEY_ID'), config.accessKeyId);
  await assert.rejects(stageLicensedArt(options), /secret configuration is invalid/);
  await writeFile(options.secretPath, '{broken-private-document');
  await assert.rejects(stageLicensedArt(options), /secret JSON is invalid/);
});

test('existing licensed directory is never overwritten', async (t) => {
  const { options } = await fixture(t);
  await writeFile(options.secretPath, JSON.stringify(config));
  await mkdir(options.destination);
  await writeFile(join(options.destination, 'keep.txt'), 'existing local art');
  await assert.rejects(stageLicensedArt(options), /Refusing to replace/);
  assert.equal(await readFile(join(options.destination, 'keep.txt'), 'utf8'), 'existing local art');
});

test('artifact and individual image tampering are rejected before staging', () => {
  const bundle = makeBundle();
  const bytes = Buffer.from(JSON.stringify(bundle));
  assert.throws(() => validateBundle(bytes, '', baseline), /must be a SHA-256/);
  assert.throws(() => validateBundle(Buffer.concat([bytes, Buffer.from(' ')]), digest(bytes), baseline), /artifact digest does not match/);
  bundle.images['chick.png'].sha256 = '0'.repeat(64);
  const tampered = Buffer.from(JSON.stringify(bundle));
  assert.throws(() => validateBundle(tampered, digest(tampered), baseline), /image digest does not match/);
});

test('unsafe filenames, invalid PNGs and missing portrait references are rejected', () => {
  const changes = [
    (bundle) => { bundle.images['../escape.png'] = bundle.images['chick.png']; },
    (bundle) => { bundle.images['CON.png'] = bundle.images['chick.png']; },
    (bundle) => { bundle.presentation.companion.portrait = 'missing.png'; },
    (bundle) => { bundle.images['chick.png'] = { base64: Buffer.from('not a PNG').toString('base64'), sha256: digest('not a PNG') }; },
    (bundle) => { bundle.images['chick.png'].base64 += '\n'; },
  ];
  for (const change of changes) {
    const bundle = makeBundle();
    change(bundle);
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateBundle(bytes, digest(bytes), baseline));
  }
});

test('incompatible presentation cannot change collection identity or shared design contract', () => {
  const changes = [
    (bundle) => { bundle.presentation.schema_version = 2; },
    (bundle) => { bundle.presentation.companion.id = 'different-economic-identity'; },
    (bundle) => { bundle.presentation.palette.paper = '#000000'; },
    (bundle) => { bundle.presentation.typography.font = '../other.ttf'; },
    (bundle) => { bundle.presentation.keepsakes = []; },
    (bundle) => { bundle.presentation.companion.label = ''; },
    (bundle) => { bundle.presentation.companion.extra = 'unrecognized'; },
  ];
  for (const change of changes) {
    const bundle = makeBundle();
    change(bundle);
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateBundle(bytes, digest(bytes), baseline));
  }
});

test('PNG dimensions, image count and bundle size are bounded', () => {
  const oversizedPng = Buffer.from(png);
  oversizedPng.writeUInt32BE(4096, 16);
  const bundle = makeBundle();
  bundle.images['chick.png'] = { sha256: digest(oversizedPng), base64: oversizedPng.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  assert.throws(() => validateBundle(bytes, digest(bytes), baseline), /dimensions/);
  for (let index = 0; index < 9; index++) bundle.images[`extra-${index}.png`] = bundle.images['bird.png'];
  const excessive = Buffer.from(JSON.stringify(bundle));
  assert.throws(() => validateBundle(excessive, digest(excessive), baseline), /image count/);
  const huge = Buffer.alloc(8 * 1024 * 1024 + 1);
  assert.throws(() => validateBundle(huge, digest(huge), baseline), /artifact size/);
});

test('S3 download uses one explicit object, reads bounded stream and destroys transport', async () => {
  let destroyed = false;
  const client = {
    async send(command, options) {
      assert.deepEqual(command.input, { Bucket: config.bucket, Key: config.key });
      assert.ok(options.abortSignal instanceof AbortSignal);
      return { ContentLength: 9, Body: Readable.from([Buffer.from('synthetic')]) };
    },
    destroy() { destroyed = true; },
  };
  assert.equal((await downloadArtifact(config, client)).toString(), 'synthetic');
  assert.equal(destroyed, true);
});

test('S3 failures and excessive unknown-length streams cannot disclose secret details', async () => {
  for (const send of [
    async () => { throw new Error(`SDK failed with ${config.secretAccessKey}`); },
    async () => ({ Body: Readable.from([Buffer.alloc(8 * 1024 * 1024 + 1)]) }),
  ]) {
    let destroyed = false;
    await assert.rejects(downloadArtifact(config, { send, destroy() { destroyed = true; } }), (error) => {
      assert.match(error.message, /Private licensed asset download failed/);
      assert.ok(!error.message.includes(config.secretAccessKey));
      return true;
    });
    assert.equal(destroyed, true);
  }
});

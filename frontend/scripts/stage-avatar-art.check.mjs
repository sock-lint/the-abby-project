import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';

const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cRZ8AAAAASUVORK5CYII=', 'base64');
const config = {
  endpoint: 'https://synthetic-storage.invalid', bucket: 'synthetic-private', key: 'private/synthetic-avatar.json',
  region: 'us-east-1', accessKeyId: 'synthetic-key', secretAccessKey: 'synthetic-secret',
};

function makeGlb(parts, modify = () => {}) {
  const document = {
    asset: { version: '2.0' }, scene: 0,
    scenes: [{ nodes: Array.from({ length: 7 }, (_, index) => index) }],
    nodes: [parts.body, parts.head, parts.face, ...Object.values(parts.hair)].map((name) => ({ name, mesh: 0 })),
    meshes: [{ primitives: [{ attributes: { POSITION: 0, TEXCOORD_0: 1 } }] }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [0, 0, 0], max: [1, 1, 0] },
      { bufferView: 1, componentType: 5126, count: 3, type: 'VEC2' },
    ],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36 }, { buffer: 0, byteOffset: 36, byteLength: 24 }], buffers: [{ byteLength: 60 }],
  };
  modify(document);
  const json = Buffer.from(JSON.stringify(document));
  const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, ' ');
  json.copy(padded);
  const binary = Buffer.alloc(60);
  binary.writeFloatLE(1, 12);
  binary.writeFloatLE(1, 28);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + padded.length + binary.length, 8);
  header.writeUInt32LE(padded.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binaryHeader = Buffer.alloc(8);
  binaryHeader.writeUInt32LE(binary.length, 0);
  binaryHeader.writeUInt32LE(0x004e4942, 4);
  return Buffer.concat([header, padded, binaryHeader, binary]);
}

function makeBundle() {
  const parts = { body: 'Archer_Body', head: 'Archer_Head', face: 'Archer_Face', hair: {} };
  for (let index = 1; index <= 4; index++) parts.hair[`hair-0${index}`] = `Archer_Hair_0${index}`;
  const textures = { outfit: {}, hair: {}, face: {} };
  for (const skin of ['fair', 'tan']) for (const outfit of ['nature', 'aqua', 'fire', 'dark']) textures.outfit[`${skin}:${outfit}`] = `${skin}-${outfit}.png`;
  for (const color of ['dark', 'light']) { textures.hair[color] = `hair-${color}.png`; textures.face[color] = `face-${color}.png`; }
  const manifest = {
    schema_version: 1, delivery_review: 'public_runtime_accepted', delivery_review_reference: 'synthetic-owner-acceptance',
    models: { archer: { file: 'archer.glb', idle_clip: null, rotation_y: 0 } }, parts, textures,
  };
  const glb = makeGlb(parts);
  const files = { 'archer.glb': { sha256: digest(glb), base64: glb.toString('base64') } };
  for (const name of [...Object.values(textures.outfit), ...Object.values(textures.hair), ...Object.values(textures.face)]) files[name] = { sha256: digest(png), base64: png.toString('base64') };
  return { schema_version: 1, manifest, files };
}

async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'abby-avatar-art-test-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const bytes = Buffer.from(JSON.stringify(makeBundle()));
  return { root, bytes, options: {
    secretPath: join(root, 'ABBY_AVATAR_ASSETS'), destination: join(root, 'licensed'),
    expectedHash: digest(bytes), required: false,
    download: async (received) => { assert.deepEqual(received, config); return bytes; },
  } };
}

test('production build stages the avatar before Vite and excludes local paid art', async () => {
  const dockerfile = await readFile(new URL('../../Dockerfile', import.meta.url), 'utf8');
  assert.ok(dockerfile.includes('node scripts/stage-avatar-art.mjs'), 'Production must stage the Archer assets before Vite resolves its globs');
  assert.ok(dockerfile.indexOf('node scripts/stage-avatar-art.mjs') < dockerfile.indexOf('RUN npm run build'));
  for (const name of ['ABBY_AVATAR_ASSETS', 'ABBY_AVATAR_ASSETS_SHA256', 'ABBY_AVATAR_ASSETS_REQUIRED']) assert.match(dockerfile, new RegExp(`id=${name}(?:\\s|\\\\)`));
  assert.match(await readFile(new URL('../../.dockerignore', import.meta.url), 'utf8'), /^frontend\/src\/avatar\/licensed\/$/m);
  const workflow = await readFile(new URL('../../.github/workflows/pr-validation.yml', import.meta.url), 'utf8');
  assert.match(workflow, /npm run test:licensed-art/);
});

test('public builds skip missing avatar secrets without downloading', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { root, options } = await fixture(t);
  options.download = async () => assert.fail('Public builds must not fetch paid art');
  assert.deepEqual(await stageAvatarArt(options), { staged: false, fileCount: 0 });
  assert.ok(!(await readdir(root)).includes('licensed'));
});

test('required avatar assets fail closed through ARG and Coolify secret', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { root, options } = await fixture(t);
  await assert.rejects(stageAvatarArt({ ...options, required: true }), /missing/i);
  await writeFile(join(root, 'ABBY_AVATAR_ASSETS_REQUIRED'), 'true');
  await assert.rejects(stageAvatarArt(options), /missing/i);
});

test('accepted avatar stages exact runtime files, resolving every appearance through a Vite build', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { root, options } = await fixture(t);
  await writeFile(options.secretPath, JSON.stringify(config));
  // Coolify transports build-time digests as secret files when configured.
  await writeFile(join(root, 'ABBY_AVATAR_ASSETS_SHA256'), digest(Buffer.from(JSON.stringify(makeBundle()))));
  assert.deepEqual(await stageAvatarArt({ ...options, expectedHash: '' }), { staged: true, fileCount: 13 });
  assert.deepEqual((await readdir(options.destination)).sort(), ['manifest.json', ...Object.keys(makeBundle().files)].sort());
  const source = join(root, 'src');
  await mkdir(source);
  for (const name of ['appearance.js', 'preferences.js']) await writeFile(join(source, name), await readFile(new URL(`../src/avatar/${name}`, import.meta.url)));
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const modelBytes = await readFile(join(options.destination, 'archer.glb'));
  const loaded = await new GLTFLoader().parseAsync(modelBytes.buffer.slice(modelBytes.byteOffset, modelBytes.byteOffset + modelBytes.byteLength), '');
  const parts = makeBundle().manifest.parts;
  for (const name of [parts.body, parts.head, parts.face, ...Object.values(parts.hair)]) assert.ok(loaded.scene.getObjectByName(name)?.isMesh);
  await rename(options.destination, join(source, 'licensed'));
  const { build } = await import('vite');
  const output = await build({
    configFile: false, logLevel: 'silent', root, base: '/static/',
    build: { write: false, assetsInlineLimit: 0, lib: { entry: join(source, 'appearance.js'), formats: ['es'] } },
  });
  const entries = (Array.isArray(output) ? output : [output]).flatMap((result) => result.output);
  const code = entries.find((entry) => entry.type === 'chunk' && entry.isEntry).code;
  const { resolveAvatarAppearance } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  for (const hair_style of ['hair-01', 'hair-02', 'hair-03', 'hair-04']) for (const hair_color of ['dark', 'light']) for (const skin_tone of ['fair', 'tan']) for (const outfit of ['nature', 'aqua', 'fire', 'dark']) {
    const appearance = resolveAvatarAppearance({ hair_style, hair_color, skin_tone, outfit });
    assert.ok(appearance, `${hair_style}/${hair_color}/${skin_tone}/${outfit} must render`);
    assert.equal(appearance.hairStyle, hair_style);
    assert.ok(appearance.url);
    assert.ok(Object.values(appearance.textures).every(Boolean));
  }
});

test('accepted export metadata remains compatible without changing runtime identity', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeBundle();
  Object.assign(bundle.manifest, {
    license_url: 'https://synthetic-publisher.invalid/license',
    defaults: { hair_style: 'hair-01', hair_color: 'dark', skin_tone: 'fair', outfit: 'nature' },
    capabilities: { static_pose: true, animation: false, weapons: false, fitted_creature_clothing: false },
    texture_metadata: Object.fromEntries(Object.entries(bundle.files).filter(([name]) => name.endsWith('.png')).map(([name, file]) => [name, { sha256: file.sha256, bytes: png.length, publisher_tint: [1, 1, 1, 1] }])),
  });
  Object.assign(bundle.manifest.models.archer, { bytes: Buffer.from(bundle.files['archer.glb'].base64, 'base64').length, sha256: bundle.files['archer.glb'].sha256, skin_count: 1, clips: [], scale: 1 });
  const bytes = Buffer.from(JSON.stringify(bundle));
  const accepted = validateAvatarBundle(bytes, digest(bytes));
  assert.deepEqual(accepted.manifest.parts, bundle.manifest.parts);
  assert.deepEqual(accepted.manifest.textures, bundle.manifest.textures);
  assert.equal(accepted.manifest.models.archer.file, 'archer.glb');
  assert.equal(accepted.files.size, 13);
});

test('private export metadata never enters the eagerly imported runtime manifest', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { options } = await fixture(t);
  const bundle = makeBundle();
  bundle.manifest.private_evidence = { credential: 'synthetic-sensitive-marker', source_fbx_base64: 'synthetic-original-pack-marker' };
  bundle.manifest.models.archer.export_evidence = 'synthetic-model-private-marker';
  bundle.manifest.parts.hair = { ...bundle.manifest.parts.hair };
  const bytes = Buffer.from(JSON.stringify(bundle));
  await writeFile(options.secretPath, JSON.stringify(config));
  await stageAvatarArt({ ...options, expectedHash: digest(bytes), download: async () => bytes });
  const runtime = await readFile(join(options.destination, 'manifest.json'), 'utf8');
  assert.ok(!runtime.includes('synthetic-sensitive-marker'));
  assert.ok(!runtime.includes('synthetic-original-pack-marker'));
  assert.ok(!runtime.includes('synthetic-model-private-marker'));
  assert.deepEqual(Object.keys(JSON.parse(runtime)).sort(), ['models', 'parts', 'schema_version', 'textures']);
});

test('unreviewed delivery, incomplete choices and unsafe or extra files cannot stage', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (bundle) => { bundle.manifest.delivery_review = 'private_evaluation'; },
    (bundle) => { delete bundle.manifest.delivery_review_reference; },
    (bundle) => { delete bundle.manifest.textures.outfit['tan:fire']; },
    (bundle) => { delete bundle.manifest.parts.hair['hair-04']; },
    (bundle) => { bundle.manifest.models.archer.idle_clip = 'Unaccepted Idle'; },
    (bundle) => { bundle.files['../escape.png'] = bundle.files['fair-nature.png']; },
    (bundle) => { bundle.files['unneeded.png'] = bundle.files['fair-nature.png']; },
    (bundle) => { delete bundle.files['face-light.png']; },
    (bundle) => { bundle.files['hair-dark.png'].sha256 = '0'.repeat(64); },
    (bundle) => { bundle.files['hair-dark.png'].base64 += '\n'; },
  ]) {
    const bundle = makeBundle(); change(bundle);
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('external GLB dependencies, missing mesh parts, and malformed GLB or PNG fail validation', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document) => { document.buffers[0].uri = 'https://unreviewed.invalid/model.bin'; },
    (document) => { document.images = [{ uri: 'data:image/png;base64,unreviewed' }]; },
    (document) => { document.nodes[0].name = 'Missing Body'; },
    (document) => { document.extensionsUsed = ['KHR_unreviewed']; },
  ]) {
    const bundle = makeBundle(); const glb = makeGlb(bundle.manifest.parts, change);
    bundle.files['archer.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
  for (const name of ['archer.glb', 'hair-dark.png']) {
    const bundle = makeBundle(); const bad = Buffer.from('invalid synthetic file');
    bundle.files[name] = { sha256: digest(bad), base64: bad.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('existing art is preserved and invalid secrets never fall back silently', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { options } = await fixture(t);
  await writeFile(options.secretPath, JSON.stringify(config));
  await mkdir(options.destination); await writeFile(join(options.destination, 'keep.txt'), 'local art');
  await assert.rejects(stageAvatarArt(options), /replace|exist/i);
  assert.equal(await readFile(join(options.destination, 'keep.txt'), 'utf8'), 'local art');
  await writeFile(options.secretPath, '{invalid');
  await assert.rejects(stageAvatarArt(options));
});

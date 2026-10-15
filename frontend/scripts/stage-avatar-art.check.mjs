import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+cRZ8AAAAASUVORK5CYII=', 'base64');
const config = {
  endpoint: 'https://synthetic-storage.invalid', bucket: 'synthetic-private', key: 'private/synthetic-avatar.json',
  region: 'us-east-1', accessKeyId: 'synthetic-key', secretAccessKey: 'synthetic-secret',
};

async function copyAvatarRuntime(root) {
  const source = join(root, 'src/avatar');
  await mkdir(source, { recursive: true });
  for (const name of ['appearance.js', 'preferences.js', 'sharedRelease.js']) {
    await writeFile(join(source, name), await readFile(new URL(`../src/avatar/${name}`, import.meta.url)));
  }
  await writeFile(join(root, 'assets.lock.json'), await readFile(new URL('../assets.lock.json', import.meta.url)));
  return source;
}
const runtimeResolution = { alias: { '@abby-assets/contracts': fileURLToPath(new URL('../node_modules/@abby-assets/contracts/index.js', import.meta.url)) } };

function makeGlb(parts, modify = () => {}) {
  const wardrobeNames = parts.wardrobe ? [parts.wardrobe.hair_for_hat,
    ...['headwear', 'mask', 'bow', 'quiver'].flatMap((slot) => Object.values(parts.wardrobe[slot]))] : [];
  const names = [parts.body, ...(typeof parts.head === 'string' ? [parts.head] : Object.values(parts.head)), parts.face, ...Object.values(parts.hair), ...wardrobeNames];
  const document = {
    asset: { version: '2.0' }, scene: 0,
    scenes: [{ nodes: names.map((_name, index) => index) }],
    nodes: names.map((name) => ({ name, mesh: 0 })),
    meshes: [{ primitives: [{ attributes: { POSITION: 0, TEXCOORD_0: 1 } }] }],
    accessors: [
      { bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [0, 0, 0], max: [1, 1, 0] },
      { bufferView: 1, componentType: 5126, count: 3, type: 'VEC2' },
    ],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36 }, { buffer: 0, byteOffset: 36, byteLength: 24 }], buffers: [{ byteLength: 60 }],
  };
  const suppliedBinary = modify(document);
  const json = Buffer.from(JSON.stringify(document));
  const padded = Buffer.alloc(Math.ceil(json.length / 4) * 4, ' ');
  json.copy(padded);
  const binary = Buffer.isBuffer(suppliedBinary) ? suppliedBinary : Buffer.alloc(60);
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

// Synthetic skinned triangle with a rigidly attached head/hair. This exercises
// the real glTF loader/mixer, and is not evidence about the purchased Archer.
function makeIdleGlb(parts, change = () => {}) {
  return makeGlb(parts, (document) => {
    document.meshes.push(structuredClone(document.meshes[0]));
    for (const node of document.nodes.slice(1)) node.mesh = 1;
    document.nodes[0].skin = 0;
    const headBone = document.nodes.length;
    document.nodes.push({ name: 'Head', children: document.nodes.map((_node, index) => index).slice(1) });
    document.scenes[0].nodes = [0, headBone];
    Object.assign(document.meshes[0].primitives[0].attributes, { JOINTS_0: 2, WEIGHTS_0: 3 });
    document.bufferViews.push(
      { buffer: 0, byteOffset: 60, byteLength: 12 },
      { buffer: 0, byteOffset: 72, byteLength: 48 },
      { buffer: 0, byteOffset: 120, byteLength: 64 },
      { buffer: 0, byteOffset: 184, byteLength: 8 },
      { buffer: 0, byteOffset: 192, byteLength: 32 },
    );
    document.accessors.push(
      { bufferView: 2, componentType: 5121, count: 3, type: 'VEC4' },
      { bufferView: 3, componentType: 5126, count: 3, type: 'VEC4' },
      { bufferView: 4, componentType: 5126, count: 1, type: 'MAT4' },
      { bufferView: 5, componentType: 5126, count: 2, type: 'SCALAR', min: [0], max: [1] },
      { bufferView: 6, componentType: 5126, count: 2, type: 'VEC4' },
    );
    document.buffers[0].byteLength = 224;
    document.skins = [{ joints: [headBone], skeleton: headBone, inverseBindMatrices: 4 }];
    document.animations = [{ name: 'Idle', samplers: [{ input: 5, output: 6, interpolation: 'LINEAR' }], channels: [{ sampler: 0, target: { node: headBone, path: 'rotation' } }] }];
    const binary = Buffer.alloc(224);
    for (let vertex = 0; vertex < 3; vertex++) binary.writeFloatLE(1, 72 + vertex * 16);
    for (let diagonal = 0; diagonal < 4; diagonal++) binary.writeFloatLE(1, 120 + diagonal * 20);
    binary.writeFloatLE(1, 188);
    binary.writeFloatLE(1, 204);
    binary.writeFloatLE(Math.sin(Math.PI / 8), 216);
    binary.writeFloatLE(Math.cos(Math.PI / 8), 220);
    const modified = change(document, binary);
    return Buffer.isBuffer(modified) ? modified : binary;
  });
}

function makeFiveInfluenceGlb(parts, change = () => {}) {
  return makeIdleGlb(parts, (document, original) => {
    const movingJoint = document.skins[0].joints[0];
    const stationaryJoints = Array.from({ length: 4 }, (_, index) => {
      const node = document.nodes.length;
      document.nodes.push({ name: `StationaryWeightJoint${index}` });
      document.scenes[0].nodes.push(node);
      return node;
    });
    document.skins[0].joints = [...stationaryJoints, movingJoint];
    delete document.skins[0].inverseBindMatrices;
    Object.assign(document.meshes[0].primitives[0].attributes, { JOINTS_1: 7, WEIGHTS_1: 8 });
    document.bufferViews.push(
      { buffer: 0, byteOffset: 224, byteLength: 12 },
      { buffer: 0, byteOffset: 236, byteLength: 48 },
    );
    document.accessors.push(
      { bufferView: 7, componentType: 5121, count: 3, type: 'VEC4' },
      { bufferView: 8, componentType: 5126, count: 3, type: 'VEC4' },
    );
    document.buffers[0].byteLength = 284;
    const binary = Buffer.alloc(284);
    original.copy(binary);
    // Only the fifth influence on vertex 1 moves. Keeping all five original
    // weights checks the combined sum without normalizing either set alone.
    const weights = [0.4, 0.25, 0.15, 0.12, 0.08];
    for (let influence = 0; influence < 4; influence++) {
      binary[64 + influence] = influence;
      binary.writeFloatLE(weights[influence], 88 + influence * 4);
    }
    binary[228] = 4;
    binary.writeFloatLE(weights[4], 252);
    change(document, binary);
    return binary;
  });
}

function makeExpandedBundle() {
  const legacy = makeBundle();
  const parts = { ...legacy.manifest.parts, head: { 'head-01': 'Archer_Head_01', 'head-02': 'Archer_Head_02' } };
  const textures = { outfit: {}, hair: {}, face: {} };
  for (const style of ['archer-01', 'archer-02', 'archer-03']) {
    for (const [key, file] of Object.entries(legacy.manifest.textures.outfit)) textures.outfit[`${style}:${key}`] = file;
  }
  for (const color of ['dark', 'light', 'brown', 'orange', 'grey']) {
    textures.hair[color] = `hair-${color}.png`;
    for (const style of ['face-01', 'face-02', 'face-03']) textures.face[`${style}:${color}`] = `${style}-${color}.png`;
  }
  const models = {};
  const files = {};
  for (const style of ['archer-01', 'archer-02', 'archer-03']) {
    const glb = makeIdleGlb(parts, (document) => { document.asset.generator = `synthetic-${style}`; });
    models[style] = {
      file: `${style}.glb`, idle_clip: 'Idle', rotation_y: 0,
      animation_source_sha256: 'a'.repeat(64), animation_review_reference: 'synthetic-idle-review',
      animation_validation: {
        method: 'supplied-hierarchy-rotation-retarget-v1', duration_seconds: 1, sampled_frames: 3, moving_vertices: 1,
        head_attachment_error: 0, reimport_max_vertex_error: 0, source_rest_joint_difference: 0.1445,
        target_joint_error: 0, rotation_delta_error: 0, nonroot_translation_variation: 0, source_scale_variation: 0,
      },
    };
    files[`${style}.glb`] = { sha256: digest(glb), base64: glb.toString('base64') };
  }
  for (const file of new Set(Object.values(textures).flatMap(Object.values))) files[file] = { sha256: digest(png), base64: png.toString('base64') };
  return {
    schema_version: 1,
    manifest: { ...legacy.manifest, schema_version: 2, models, parts, textures }, files,
  };
}

function makeWardrobeGlb(parts, change = () => {}) {
  return makeIdleGlb(parts, (document, binary) => {
    const headIndex = document.nodes.findIndex((node) => node.name === 'Head');
    const head = document.nodes[headIndex];
    head.name = 'RigHead';
    const bowNodes = Object.values(parts.wardrobe.bow).map((name) => document.nodes.findIndex((node) => node.name === name));
    const quiverNodes = Object.values(parts.wardrobe.quiver).map((name) => document.nodes.findIndex((node) => node.name === name));
    head.children = head.children.filter((index) => !bowNodes.includes(index) && !quiverNodes.includes(index));
    const palmIndex = document.nodes.length;
    const ribcageIndex = palmIndex + 1;
    document.nodes.push({ name: 'RigLPalm', children: bowNodes }, { name: 'RigRibcage', children: quiverNodes });
    document.scenes[0].nodes.push(palmIndex, ribcageIndex);
    document.skins[0].joints = [headIndex, palmIndex, ribcageIndex];
    delete document.skins[0].inverseBindMatrices;
    return change(document, binary) || binary;
  });
}

function makeWardrobeBundle() {
  const bundle = makeExpandedBundle();
  bundle.manifest.schema_version = 3;
  const wardrobe = {
    hair_for_hat: 'Archer_Hair_For_Hat',
    headwear: { 'crown-eve': 'Archer_Crown_Eve', 'hood-mystical': 'Archer_Hood_Mystical' },
    mask: { 'mask-undercover': 'Archer_Mask_Undercover' },
    bow: { 'bow-greenhorn': 'Archer_Bow_Greenhorn', 'bow-vines': 'Archer_Bow_Vines', 'bow-myth': 'Archer_Bow_Myth' },
    quiver: { 'quiver-angel': 'Archer_Quiver_Angel', 'quiver-rook': 'Archer_Quiver_Rook', 'quiver-tale': 'Archer_Quiver_Tale' },
  };
  bundle.manifest.parts.wardrobe = wardrobe;
  bundle.manifest.textures.wardrobe = {};
  for (const slot of ['headwear', 'mask', 'bow', 'quiver']) for (const style of Object.keys(wardrobe[slot])) {
    for (const palette of ['aqua', 'nature', 'fire', 'dark']) {
      const neutral = ['bow-greenhorn', 'quiver-rook'].includes(style);
      const file = `${style}-${neutral ? 'neutral' : palette}.png`;
      bundle.manifest.textures.wardrobe[`${style}:${palette}`] = file;
      bundle.files[file] = { sha256: digest(png), base64: png.toString('base64') };
    }
  }
  for (const model of Object.values(bundle.manifest.models)) {
    const glb = makeWardrobeGlb(bundle.manifest.parts, (document) => { document.asset.generator = `synthetic-${model.file}`; });
    bundle.files[model.file] = { sha256: digest(glb), base64: glb.toString('base64') };
  }
  return bundle;
}

test('wardrobe stages complete modules and supplied palette aliases without private metadata', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeWardrobeBundle();
  bundle.manifest.wardrobe_source_report = { private_path: '/private/synthetic-source', source_sha256: 'b'.repeat(64) };
  const bytes = Buffer.from(JSON.stringify(bundle));
  const { manifest, files } = validateAvatarBundle(bytes, digest(bytes));
  assert.equal(manifest.schema_version, 3);
  assert.equal(files.size, 61);
  assert.deepEqual(manifest.parts, bundle.manifest.parts);
  assert.deepEqual(manifest.textures, bundle.manifest.textures);
  assert.deepEqual(Object.keys(manifest).sort(), ['models', 'parts', 'schema_version', 'textures']);
  assert.ok(!JSON.stringify(manifest).includes('synthetic-source'));
  assert.equal(manifest.textures.wardrobe['bow-greenhorn:aqua'], manifest.textures.wardrobe['bow-greenhorn:fire']);
  assert.equal(manifest.textures.wardrobe['quiver-rook:nature'], manifest.textures.wardrobe['quiver-rook:dark']);
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  for (const model of Object.values(manifest.models)) {
    assert.deepEqual(Object.keys(model).sort(), ['file', 'idle_clip', 'rotation_y']);
    const glb = files.get(model.file);
    const loaded = await new GLTFLoader().parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
    for (const name of [manifest.parts.wardrobe.hair_for_hat,
      ...['headwear', 'mask', 'bow', 'quiver'].flatMap((slot) => Object.values(manifest.parts.wardrobe[slot]))]) {
      const module = loaded.scene.getObjectByName(name);
      assert.ok(module?.isMesh, `${model.file} contains ${name}`);
      assert.ok(module.parent.isBone, `${name} follows the synthetic supplied skeleton`);
    }
  }
});

test('wardrobe rejects missing modules, palette mappings, duplicate names and unknown slots', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (bundle) => { delete bundle.manifest.parts.wardrobe; },
    (bundle) => { delete bundle.manifest.parts.wardrobe.hair_for_hat; },
    (bundle) => { delete bundle.manifest.parts.wardrobe.headwear['hood-mystical']; },
    (bundle) => { bundle.manifest.parts.wardrobe.bow.none = 'Archer_No_Bow'; },
    (bundle) => { bundle.manifest.parts.wardrobe.quiver['quiver-unowned'] = 'Archer_Unowned_Quiver'; },
    (bundle) => { bundle.manifest.parts.wardrobe.hair_for_hat = bundle.manifest.parts.hair['hair-01']; },
    (bundle) => { bundle.manifest.parts.wardrobe.mask['mask-undercover'] = bundle.manifest.parts.body; },
    (bundle) => { delete bundle.manifest.textures.wardrobe['crown-eve:dark']; },
    (bundle) => { delete bundle.manifest.textures.wardrobe['bow-greenhorn:fire']; },
    (bundle) => { bundle.manifest.textures.wardrobe['bow-myth:unreviewed'] = 'extra.png'; },
    (bundle) => { bundle.manifest.textures.wardrobe['hood-mystical:fire'] = '../source.psd'; },
  ]) {
    const bundle = makeWardrobeBundle(); change(bundle);
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
  for (const name of ['Archer_Hair_For_Hat', 'Archer_Bow_Myth', 'Archer_Hood_Mystical', 'Archer_Quiver_Tale']) {
    const bundle = makeWardrobeBundle();
    const glb = makeWardrobeGlb(bundle.manifest.parts, (document) => {
      delete document.nodes.find((node) => node.name === name).mesh;
    });
    bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)), /selected mesh part/);
  }
});

test('wardrobe cannot stage extra visible geometry or detach modules from their supplied bone', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document) => {
      document.scenes[0].nodes.push(document.nodes.length);
      document.nodes.push({ name: 'UnlistedExtraModule', mesh: 1 });
    },
    (document) => {
      const module = document.nodes.findIndex((node) => node.name === 'Archer_Hood_Mystical');
      document.nodes.find((node) => node.name === 'RigHead').children = document.nodes.find((node) => node.name === 'RigHead').children.filter((index) => index !== module);
      document.scenes[0].nodes.push(module);
    },
    (document) => {
      const module = document.nodes.findIndex((node) => node.name === 'Archer_Bow_Myth');
      document.nodes.find((node) => node.name === 'RigLPalm').children = document.nodes.find((node) => node.name === 'RigLPalm').children.filter((index) => index !== module);
      document.nodes.find((node) => node.name === 'RigHead').children.push(module);
    },
    (document) => {
      const module = document.nodes.findIndex((node) => node.name === 'Archer_Quiver_Tale');
      document.nodes.find((node) => node.name === 'RigRibcage').children = document.nodes.find((node) => node.name === 'RigRibcage').children.filter((index) => index !== module);
      document.nodes.find((node) => node.name === 'RigHead').children.push(module);
    },
    (document) => {
      // The body skin weights target RigHead; assigning them to a bow must
      // not pass merely because its skin references the right whole rig.
      document.nodes.find((node) => node.name === 'Archer_Bow_Vines').mesh = 0;
      document.nodes.find((node) => node.name === 'Archer_Bow_Vines').skin = 0;
    },
  ]) {
    const bundle = makeWardrobeBundle();
    const glb = makeWardrobeGlb(bundle.manifest.parts, change);
    bundle.files['archer-01.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)), /wardrobe|undeclared/);
  }
});

test('wardrobe mesh aliases cannot collide with loader dictionaries or change during name sanitization', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const name of ['__proto__', 'constructor', 'toString', 'Crown.Eve', 'Crown/Eve', 'Crown:Eve', 'Crown[Eve]']) {
    const bundle = makeWardrobeBundle();
    bundle.manifest.parts.wardrobe.headwear['crown-eve'] = name;
    const glb = makeWardrobeGlb(bundle.manifest.parts, (document) => {
      const crown = document.nodes.findIndex((node) => node.name === name);
      document.nodes.find((node) => node.name === 'RigHead').children = document.nodes.find((node) => node.name === 'RigHead').children.filter((index) => index !== crown);
      document.scenes[0].nodes.push(crown);
    });
    for (const model of Object.values(bundle.manifest.models)) bundle.files[model.file] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)), /mesh parts|wardrobe/);
  }
});

test('wardrobe preserves rigid skinned modules bound to the matching body bone', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeWardrobeBundle();
  const glb = makeWardrobeGlb(bundle.manifest.parts, (document, binary) => {
    const jointAccessor = document.accessors.length;
    const jointView = document.bufferViews.length;
    document.bufferViews.push({ buffer: 0, byteOffset: binary.length, byteLength: 12 });
    document.accessors.push({ bufferView: jointView, componentType: 5121, count: 3, type: 'VEC4' });
    const geometry = structuredClone(document.meshes[0]);
    geometry.primitives[0].attributes.JOINTS_0 = jointAccessor;
    const bow = document.nodes.find((node) => node.name === 'Archer_Bow_Myth');
    bow.mesh = document.meshes.length;
    bow.skin = 0;
    document.meshes.push(geometry);
    // Skin joint index1 is RigLPalm, with the original normalized [1,0,0,0]
    // weights. The body retains its separate RigHead joint attributes.
    const result = Buffer.concat([binary, Buffer.alloc(12, 1)]);
    document.buffers[0].byteLength = result.length;
    return result;
  });
  bundle.files['archer-01.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  const validated = validateAvatarBundle(bytes, digest(bytes));
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const loaded = await new GLTFLoader().parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
  const bow = loaded.scene.getObjectByName(validated.manifest.parts.wardrobe.bow['bow-myth']);
  assert.ok(bow.isSkinnedMesh);
  assert.equal(bow.skeleton.bones[bow.geometry.attributes.skinIndex.getX(0)].name, 'RigLPalm');
});

test('wardrobe runtime resolves all 276480 choices through a Vite build', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { root, options } = await fixture(t);
  const bundle = makeWardrobeBundle();
  const bytes = Buffer.from(JSON.stringify(bundle));
  await writeFile(options.secretPath, JSON.stringify(config));
  assert.deepEqual(await stageAvatarArt({ ...options, expectedHash: digest(bytes), download: async () => bytes }), { staged: true, fileCount: 61 });
  const source = await copyAvatarRuntime(root);
  await rename(options.destination, join(source, 'licensed'));
  const { build } = await import('vite');
  const output = await build({ configFile: false, logLevel: 'silent', root, base: '/static/', resolve: runtimeResolution,
    build: { write: false, assetsInlineLimit: 0, lib: { entry: join(source, 'appearance.js'), formats: ['es'] } } });
  const entries = (Array.isArray(output) ? output : [output]).flatMap((result) => result.output);
  const code = entries.find((entry) => entry.type === 'chunk' && entry.isEntry).code;
  const { resolveAvatarAppearance } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  const expectedModels = Object.fromEntries(Object.entries(bundle.manifest.models).map(([style, model]) =>
    [style, `data:model/gltf-binary;base64,${bundle.files[model.file].base64}`]));
  const expectedImage = `data:image/png;base64,${png.toString('base64')}`;
  let count = 0;
  for (const outfit_style of ['archer-01', 'archer-02', 'archer-03']) for (const hair_style of ['hair-01', 'hair-02', 'hair-03', 'hair-04'])
    for (const hair_color of ['dark', 'light', 'brown', 'orange', 'grey']) for (const face_style of ['face-01', 'face-02', 'face-03'])
      for (const head_style of ['head-01', 'head-02']) for (const skin_tone of ['fair', 'tan']) for (const outfit of ['aqua', 'nature', 'fire', 'dark']) {
      for (const headwear_style of ['none', 'crown-eve', 'hood-mystical']) for (const mask_style of ['none', 'mask-undercover'])
        for (const bow_style of ['none', 'bow-greenhorn', 'bow-vines', 'bow-myth']) for (const quiver_style of ['none', 'quiver-angel', 'quiver-rook', 'quiver-tale']) {
          const preferences = { outfit_style, hair_style, hair_color, face_style, head_style, skin_tone, outfit, headwear_style, mask_style, bow_style, quiver_style };
          const appearance = resolveAvatarAppearance(preferences);
          assert.ok(appearance, JSON.stringify(preferences));
          assert.equal(appearance.url, expectedModels[outfit_style]);
          assert.equal(appearance.idleClip, 'Idle');
          assert.equal(appearance.hairStyle, hair_style);
          assert.equal(appearance.headStyle, head_style);
          let selectedSlots = 0;
          for (const slot of ['headwear', 'mask', 'bow', 'quiver']) {
            const style = preferences[`${slot}_style`];
            assert.equal(appearance.wardrobe[slot], style);
            assert.equal(Object.hasOwn(appearance.textures, slot), style !== 'none');
            if (style !== 'none') {
              selectedSlots++;
              assert.equal(appearance.textures[slot], expectedImage);
              assert.equal(appearance.parts.wardrobe[slot][style], bundle.manifest.parts.wardrobe[slot][style]);
            }
          }
          assert.equal(Object.keys(appearance.textures).length, 3 + selectedSlots);
          count++;
        }
    }
  assert.equal(count, 276480);
  assert.ok(!code.includes('synthetic-owner-acceptance'));
  assert.ok(!code.includes('synthetic-idle-review'));
});

test('expanded costumes stage only reviewed supplied idle and matching palettes', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeExpandedBundle();
  const bytes = Buffer.from(JSON.stringify(bundle));
  const { manifest, files } = validateAvatarBundle(bytes, digest(bytes));
  assert.deepEqual(manifest.textures, bundle.manifest.textures);
  assert.equal(files.size, 31);
  assert.equal(manifest.schema_version, 2);
  for (const style of ['archer-01', 'archer-02', 'archer-03']) {
    assert.deepEqual(manifest.models[style], { file: `${style}.glb`, idle_clip: 'Idle', rotation_y: 0 });
  }
  assert.ok(!JSON.stringify(manifest).includes('synthetic-idle-review'));
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { AnimationMixer, Vector3 } = await import('three');
  const glb = files.get('archer-03.glb');
  const loaded = await new GLTFLoader().parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
  const body = loaded.scene.getObjectByName(bundle.manifest.parts.body);
  assert.ok(body.isSkinnedMesh);
  loaded.scene.updateMatrixWorld(true);
  const initial = body.applyBoneTransform(1, new Vector3(1, 0, 0)).clone();
  const mixer = new AnimationMixer(loaded.scene);
  mixer.clipAction(loaded.animations[0]).play();
  mixer.update(0.5);
  loaded.scene.updateMatrixWorld(true);
  assert.ok(initial.distanceTo(body.applyBoneTransform(1, new Vector3(1, 0, 0))) > 0.1);
  for (const head of Object.values(bundle.manifest.parts.head)) assert.ok(loaded.scene.getObjectByName(head).parent.isBone);
});

test('expanded idle requires real conversion evidence and explicit review for every costume', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (bundle) => { delete bundle.manifest.models['archer-02']; },
    (bundle) => { delete bundle.manifest.models['archer-02'].animation_review_reference; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_source_sha256 = 'unverified'; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.moving_vertices = 0; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.method = 'supplied-world-rest-delta-v1'; },
    (bundle) => { delete bundle.manifest.models['archer-02'].animation_validation.target_joint_error; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.rest_joint_error = 0; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.target_joint_error = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.rotation_delta_error = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.nonroot_translation_variation = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.source_scale_variation = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.source_rest_joint_difference = -1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.source_rest_joint_difference = NaN; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.head_attachment_error = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.reimport_max_vertex_error = 1; },
    (bundle) => { bundle.manifest.models['archer-02'].animation_validation.reimport_max_vertex_error = NaN; },
    (bundle) => { bundle.manifest.models['archer-02'].file = 'archer-01.glb'; },
    (bundle) => { delete bundle.manifest.textures.outfit['archer-03:tan:fire']; },
    (bundle) => { delete bundle.manifest.textures.face['face-03:grey']; },
    (bundle) => { delete bundle.manifest.parts.head['head-01']; },
    (bundle) => { bundle.manifest.parts.head['head-01'] = bundle.manifest.parts.head['head-02']; },
  ]) {
    const bundle = makeExpandedBundle(); change(bundle);
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('expanded runtime resolves all 2880 choices through a Vite build', async (t) => {
  const { stageAvatarArt } = await import('./stage-avatar-art.mjs');
  const { root, options } = await fixture(t);
  const bundle = makeExpandedBundle();
  const bytes = Buffer.from(JSON.stringify(bundle));
  await writeFile(options.secretPath, JSON.stringify(config));
  assert.deepEqual(await stageAvatarArt({ ...options, expectedHash: digest(bytes), download: async () => bytes }), { staged: true, fileCount: 31 });
  const source = await copyAvatarRuntime(root);
  await rename(options.destination, join(source, 'licensed'));
  const { build } = await import('vite');
  const output = await build({ configFile: false, logLevel: 'silent', root, base: '/static/', resolve: runtimeResolution,
    build: { write: false, assetsInlineLimit: 0, lib: { entry: join(source, 'appearance.js'), formats: ['es'] } } });
  const entries = (Array.isArray(output) ? output : [output]).flatMap((result) => result.output);
  const code = entries.find((entry) => entry.type === 'chunk' && entry.isEntry).code;
  const { resolveAvatarAppearance } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
  let count = 0;
  for (const outfit_style of ['archer-01', 'archer-02', 'archer-03']) for (const hair_style of ['hair-01', 'hair-02', 'hair-03', 'hair-04'])
    for (const hair_color of ['dark', 'light', 'brown', 'orange', 'grey']) for (const face_style of ['face-01', 'face-02', 'face-03'])
      for (const head_style of ['head-01', 'head-02']) for (const skin_tone of ['fair', 'tan']) for (const outfit of ['aqua', 'nature', 'fire', 'dark']) {
      const appearance = resolveAvatarAppearance({ outfit_style, hair_style, hair_color, face_style, head_style, skin_tone, outfit });
      assert.ok(appearance, `${outfit_style}/${hair_style}/${hair_color}/${face_style}/${head_style}/${skin_tone}/${outfit}`);
      assert.equal(appearance.idleClip, 'Idle');
      assert.equal(appearance.headStyle, head_style);
      assert.equal(appearance.parts.head[appearance.headStyle], bundle.manifest.parts.head[head_style]);
      // Vite library mode inlines assets even with assetsInlineLimit=0.
      assert.match(appearance.url, /^data:model\/gltf-binary;base64,/);
      assert.equal(digest(Buffer.from(appearance.url.split(',')[1], 'base64')), bundle.files[`${outfit_style}.glb`].sha256);
      count++;
    }
  assert.equal(count, 2880);
});

test('expanded idle rejects missing, unrelated, malformed or static animation tracks', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document) => { document.animations = []; },
    (document) => { document.animations[0].name = 'Run'; },
    (document) => { document.animations.push(structuredClone(document.animations[0])); },
    (document) => { document.animations[0].channels[0].target.node = 99; },
    (document) => { document.animations[0].channels.push(structuredClone(document.animations[0].channels[0])); },
    (document) => { document.animations[0].samplers[0].input = 999; },
    (document) => { document.animations[0].samplers[0].output = 5; },
    (document) => { document.animations[0].samplers[0].interpolation = 'CUBICSPLINE'; },
    (document) => { delete document.nodes[0].skin; },
    (document) => { delete document.meshes[0].primitives[0].attributes.WEIGHTS_0; },
    (document) => { document.nodes.find((node) => node.name === 'Archer_Head_01').name = 'Missing Reviewed Head'; },
    (_document, binary) => { binary.writeFloatLE(0, 188); },
    (_document, binary) => { binary.writeFloatLE(Infinity, 188); },
    (_document, binary) => { binary.writeFloatLE(NaN, 216); },
    (_document, binary) => { binary.writeFloatLE(0, 216); binary.writeFloatLE(1, 220); },
  ]) {
    const bundle = makeExpandedBundle(); const glb = makeIdleGlb(bundle.manifest.parts, change);
    bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('expanded idle rejects unweighted joints, equivalent rotations and mismatched measured duration', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document, binary) => {
      const stationaryJoint = document.nodes.length;
      document.nodes.push({ name: 'StationaryBodyJoint' });
      document.scenes[0].nodes.push(stationaryJoint);
      document.skins[0].joints.push(stationaryJoint);
      delete document.skins[0].inverseBindMatrices;
      for (let vertex = 0; vertex < 3; vertex++) binary[60 + vertex * 4] = 1;
    },
    (_document, binary) => { binary.writeFloatLE(0, 216); binary.writeFloatLE(-1, 220); },
    (_document, binary) => { binary.writeFloatLE(0, 216); binary.writeFloatLE(1.005, 220); },
    (_document, binary) => { binary.writeFloatLE(2, 188); },
    (_document, binary) => { binary.writeFloatLE(1 / 30, 184); binary.writeFloatLE(1 + 1 / 30, 188); },
  ]) {
    const bundle = makeExpandedBundle(); const glb = makeIdleGlb(bundle.manifest.parts, change);
    bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('expanded idle requires valid normalized weights and complete joint attributes', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document) => { document.accessors[2].count = 2; },
    (document) => { document.accessors[2].type = 'VEC3'; },
    (document) => { document.accessors[2].componentType = 5120; },
    (document) => { document.accessors[2].normalized = true; },
    (document) => { document.accessors[3].count = 2; },
    (document) => { document.accessors[3].type = 'VEC3'; },
    (document) => { document.accessors[3].componentType = 5121; },
    (document) => { document.accessors[3].normalized = true; },
    (_document, binary) => { binary[60] = 1; },
    (_document, binary) => { binary.writeFloatLE(NaN, 72); },
    (_document, binary) => { binary.writeFloatLE(-1, 72); },
    (_document, binary) => { binary.writeFloatLE(0.5, 72); },
    (_document, binary) => { binary.writeFloatLE(0, 72); },
  ]) {
    const bundle = makeExpandedBundle(); const glb = makeIdleGlb(bundle.manifest.parts, change);
    bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('expanded idle accepts an animated ancestor of a weighted body joint', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeExpandedBundle();
  const glb = makeIdleGlb(bundle.manifest.parts, (document, binary) => {
    const weightedJoint = document.nodes.length;
    document.nodes.push({ name: 'WeightedBodyJoint' });
    document.nodes[document.skins[0].joints[0]].children.push(weightedJoint);
    document.skins[0].joints.push(weightedJoint);
    delete document.skins[0].inverseBindMatrices;
    for (let vertex = 0; vertex < 3; vertex++) binary[60 + vertex * 4] = 1;
  });
  bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  const accepted = validateAvatarBundle(bytes, digest(bytes));
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { AnimationMixer, Vector3 } = await import('three');
  const model = accepted.files.get('archer-02.glb');
  const loaded = await new GLTFLoader().parseAsync(model.buffer.slice(model.byteOffset, model.byteOffset + model.byteLength), '');
  const body = loaded.scene.getObjectByName(bundle.manifest.parts.body);
  loaded.scene.updateMatrixWorld(true);
  const initial = body.applyBoneTransform(1, new Vector3(1, 0, 0)).clone();
  const mixer = new AnimationMixer(loaded.scene);
  mixer.clipAction(loaded.animations[0]).play(); mixer.update(0.5); loaded.scene.updateMatrixWorld(true);
  assert.ok(initial.distanceTo(body.applyBoneTransform(1, new Vector3(1, 0, 0))) > 0.1);
});

test('expanded idle accepts normalized integer weights and unsigned-short joint indexes', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const componentType of [5121, 5123]) {
    const bundle = makeExpandedBundle();
    const glb = makeIdleGlb(bundle.manifest.parts, (document, binary) => {
      document.accessors[3].componentType = componentType;
      document.accessors[3].normalized = true;
      document.bufferViews[3].byteStride = 16;
      // The same padded view can also hold four unsigned-short joint indexes
      // after its four weights, preserving this small fixture's buffer bounds.
      if (componentType === 5123) {
        Object.assign(document.accessors[2], { bufferView: 3, byteOffset: 8, componentType: 5123 });
      }
      for (let vertex = 0; vertex < 3; vertex++) {
        const offset = 72 + vertex * 16;
        binary.fill(0, offset, offset + 16);
        if (componentType === 5121) binary.writeUInt8(255, offset);
        else binary.writeUInt16LE(65535, offset);
      }
    });
    bundle.files['archer-02.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.equal(validateAvatarBundle(bytes, digest(bytes)).files.size, 31);
  }
});

test('GLB extras cannot publish private metadata through legacy or expanded models', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const expanded of [false, true]) {
    const bundle = expanded ? makeExpandedBundle() : makeBundle();
    const factory = expanded ? makeIdleGlb : makeGlb;
    const glb = factory(bundle.manifest.parts, (document) => {
      document.asset.extras = { private_source_path: '/synthetic/private/source.fbx' };
    });
    const file = expanded ? 'archer-02.glb' : 'archer.glb';
    bundle.files[file] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

test('expanded idle preserves five influences and accepts motion contributed only by the second set', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeExpandedBundle();
  const glb = makeFiveInfluenceGlb(bundle.manifest.parts);
  bundle.files['archer-03.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  const staged = validateAvatarBundle(bytes, digest(bytes));
  assert.deepEqual(staged.files.get('archer-03.glb'), glb);
  const jsonLength = glb.readUInt32LE(12);
  const binary = glb.subarray(28 + jsonLength);
  const weights = [0, 1, 2, 3].map((component) => binary.readFloatLE(88 + component * 4));
  weights.push(binary.readFloatLE(252));
  for (const [index, expected] of [0.4, 0.25, 0.15, 0.12, 0.08].entries()) assert.ok(Math.abs(weights[index] - expected) < 0.000001);
  assert.ok(Math.abs(weights.reduce((sum, weight) => sum + weight, 0) - 1) < 0.000001);
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { AnimationMixer, Vector3 } = await import('three');
  const { prepareAvatarSkinning } = await import('../src/avatar/avatarSkinning.js');
  const loaded = await new GLTFLoader().parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
  const body = loaded.scene.getObjectByName(bundle.manifest.parts.body);
  const geometry = prepareAvatarSkinning(body);
  const mixer = new AnimationMixer(loaded.scene);
  mixer.clipAction(loaded.animations[0]).play(); mixer.update(0.5); loaded.scene.updateMatrixWorld(true);
  const expected = new Vector3(0.92 + 0.08 * Math.cos(Math.PI / 8), 0.08 * Math.sin(Math.PI / 8), 0);
  assert.ok(body.applyBoneTransform(1, new Vector3(1, 0, 0)).distanceTo(expected) < 0.000001);
  body.computeBoundingBox();
  assert.ok(Math.abs(body.boundingBox.max.x - expected.x) < 0.000001);
  geometry.dispose();
});

test('expanded paired influence sets reject integer weight storage before loader quantization', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const integerType of [5121, 5123]) {
    for (const integerSets of [[0], [1], [0, 1]]) {
      const bundle = makeExpandedBundle();
      const glb = makeFiveInfluenceGlb(bundle.manifest.parts, (document, binary) => {
        const maximum = integerType === 5121 ? 255 : 65535;
        const primary = integerType === 5121 ? [50, 50, 50, 50] : [12850, 12850, 12850, 12850];
        const extra = maximum - primary.reduce((sum, weight) => sum + weight, 0);
        for (const set of integerSets) {
          const accessor = document.accessors[set === 0 ? 3 : 8];
          accessor.componentType = integerType;
          accessor.normalized = true;
          document.bufferViews[accessor.bufferView].byteStride = 16;
        }
        const writeWeights = (set, vertex, weights) => {
          const offset = (set === 0 ? 72 : 236) + vertex * 16;
          binary.fill(0, offset, offset + 16);
          for (const [component, weight] of weights.entries()) {
            if (!integerSets.includes(set)) binary.writeFloatLE(weight / maximum, offset + component * 4);
            else if (integerType === 5121) binary.writeUInt8(weight, offset + component);
            else binary.writeUInt16LE(weight, offset + component * 2);
          }
        };
        for (let vertex = 0; vertex < 3; vertex++) {
          writeWeights(0, vertex, vertex === 1 ? primary : [maximum, 0, 0, 0]);
          writeWeights(1, vertex, vertex === 1 ? [extra, 0, 0, 0] : [0, 0, 0, 0]);
        }
      });
      bundle.files['archer-03.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
      const bytes = Buffer.from(JSON.stringify(bundle));
      assert.throws(() => validateAvatarBundle(bytes, digest(bytes)), undefined, `type ${integerType}, sets ${integerSets}`);
    }
  }
});

test('paired FLOAT weights reject a combined total the runtime cannot restore', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const { validateAvatarSkinning } = await import('../src/avatar/avatarSkinning.js');
  const bundle = makeExpandedBundle();
  const glb = makeFiveInfluenceGlb(bundle.manifest.parts, (_document, binary) => {
    for (let component = 0; component < 4; component++) binary.writeFloatLE(0, 88 + component * 4);
    binary.writeFloatLE(0.50025, 252);
    binary.writeFloatLE(0.50025, 256);
  });
  const loaded = await new GLTFLoader().parseAsync(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.byteLength), '');
  assert.throws(() => validateAvatarSkinning(loaded.scene), /cannot restore the reviewed total/);
  bundle.files['archer-03.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  assert.throws(() => validateAvatarBundle(bytes, digest(bytes)), /combined weights must be normalized/);
});

test('expanded idle accepts a skeletal ancestor of a second-set weighted joint', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  const bundle = makeExpandedBundle();
  const glb = makeFiveInfluenceGlb(bundle.manifest.parts, (document) => {
    const movingJoint = document.skins[0].joints[4];
    const descendant = document.nodes.length;
    document.nodes.push({ name: 'SecondSetWeightedDescendant' });
    document.nodes[movingJoint].children.push(descendant);
    document.skins[0].joints.push(descendant);
  });
  // The added descendant is joint5; only its positive fifth weight contributes
  // via the animated parent. Joint4 itself receives no body weights.
  const jsonLength = glb.readUInt32LE(12);
  glb[28 + jsonLength + 228] = 5;
  bundle.files['archer-03.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
  const bytes = Buffer.from(JSON.stringify(bundle));
  assert.equal(validateAvatarBundle(bytes, digest(bytes)).files.size, 31);
});

test('expanded idle rejects incomplete, malformed or excess influence sets', async () => {
  const { validateAvatarBundle } = await import('./stage-avatar-art.mjs');
  for (const change of [
    (document) => { delete document.meshes[0].primitives[0].attributes.JOINTS_1; },
    (document) => { delete document.meshes[0].primitives[0].attributes.WEIGHTS_1; },
    (document) => { document.meshes[0].primitives[0].attributes.JOINTS_2 = 7; },
    (document) => { document.meshes[0].primitives[0].attributes.WEIGHTS_2 = 8; },
    (document) => {
      const head = document.nodes.find((node) => node.name === 'Archer_Head_01');
      head.skin = 0;
      Object.assign(document.meshes[1].primitives[0].attributes, { JOINTS_0: 2, WEIGHTS_0: 3, WEIGHTS_1: 8 });
    },
    (document) => { document.accessors[7].count = 2; },
    (document) => { document.accessors[7].type = 'VEC3'; },
    (document) => { document.accessors[7].componentType = 5120; },
    (document) => { document.accessors[7].normalized = true; },
    (document) => { document.accessors[8].count = 2; },
    (document) => { document.accessors[8].type = 'VEC3'; },
    (document) => { document.accessors[8].componentType = 5121; },
    (document) => { document.accessors[8].normalized = true; },
    (_document, binary) => { binary[228] = 5; },
    (_document, binary) => { binary.writeFloatLE(NaN, 252); },
    (_document, binary) => { binary.writeFloatLE(-0.08, 252); },
    (_document, binary) => { binary.writeFloatLE(1.08, 252); },
    (_document, binary) => { binary.writeFloatLE(0.2, 252); },
  ]) {
    const bundle = makeExpandedBundle(); const glb = makeFiveInfluenceGlb(bundle.manifest.parts, change);
    bundle.files['archer-03.glb'] = { sha256: digest(glb), base64: glb.toString('base64') };
    const bytes = Buffer.from(JSON.stringify(bundle));
    assert.throws(() => validateAvatarBundle(bytes, digest(bytes)));
  }
});

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
  const source = await copyAvatarRuntime(root);
  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const modelBytes = await readFile(join(options.destination, 'archer.glb'));
  const loaded = await new GLTFLoader().parseAsync(modelBytes.buffer.slice(modelBytes.byteOffset, modelBytes.byteOffset + modelBytes.byteLength), '');
  const parts = makeBundle().manifest.parts;
  for (const name of [parts.body, parts.head, parts.face, ...Object.values(parts.hair)]) assert.ok(loaded.scene.getObjectByName(name)?.isMesh);
  await rename(options.destination, join(source, 'licensed'));
  const { build } = await import('vite');
  const output = await build({
    configFile: false, logLevel: 'silent', root, base: '/static/', resolve: runtimeResolution,
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

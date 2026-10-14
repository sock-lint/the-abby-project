import { createHash } from 'node:crypto';
import { lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { downloadArtifact } from './stage-licensed-art.mjs';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MAX_CONFIG_BYTES = 16 * 1024;
const MAX_BUNDLE_BYTES = 8 * 1024 * 1024;
const MAX_FILE_BYTES = 2 * 1024 * 1024;
const SHA256 = /^[a-f0-9]{64}$/;
const FILE_NAME = /^[a-z][a-z0-9_-]{0,63}\.(glb|png)$/;
const BASE64 = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const HAIR_STYLES = ['hair-01', 'hair-02', 'hair-03', 'hair-04'];
const HAIR_COLORS = ['dark', 'light'];
const OUTFITS = ['fair', 'tan'].flatMap((skin) => ['aqua', 'nature', 'fire', 'dark'].map((outfit) => `${skin}:${outfit}`));
const COSTUMES = ['archer-01', 'archer-02', 'archer-03'];
const FACES = ['face-01', 'face-02', 'face-03'];
const HEADS = ['head-01', 'head-02'];
const EXPANDED_HAIR_COLORS = [...HAIR_COLORS, 'brown', 'orange', 'grey'];
const WARDROBE = {
  headwear: ['crown-eve', 'hood-mystical'],
  mask: ['mask-undercover'],
  bow: ['bow-greenhorn', 'bow-vines', 'bow-myth'],
  quiver: ['quiver-angel', 'quiver-rook', 'quiver-tale'],
};
const WARDROBE_TEXTURE_KEYS = Object.values(WARDROBE).flat()
  .flatMap((style) => ['aqua', 'nature', 'fire', 'dark'].map((palette) => `${style}:${palette}`));

function fail(message) { throw new Error(message); }
function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function hasKeys(value, keys) { return object(value) && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key)); }
function text(value, limit) {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= limit
    && ![...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127);
}
function hash(bytes) { return createHash('sha256').update(bytes).digest('hex'); }
function index(value, entries) { return Number.isSafeInteger(value) && value >= 0 && value < entries.length; }
function filename(value, extension) {
  return typeof value === 'string' && FILE_NAME.test(value) && value.endsWith(extension)
    && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])\./.test(value);
}
function parseJson(bytes, message) {
  try { return JSON.parse(bytes.toString('utf8')); } catch { fail(message); }
}

async function readOptionalSecret(path) {
  try {
    const metadata = await lstat(path);
    if (!metadata.isFile() || metadata.size > MAX_CONFIG_BYTES) fail('Avatar asset secret size is invalid.');
    return await readFile(path);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return undefined;
  }
}

function validateConfig(config) {
  const keys = ['endpoint', 'bucket', 'key', 'region', 'accessKeyId', 'secretAccessKey'];
  if (!hasKeys(config, keys) || keys.some((key) => !text(config[key], key === 'key' ? 512 : MAX_CONFIG_BYTES))) {
    fail('Avatar asset secret configuration is invalid.');
  }
  let endpoint;
  try { endpoint = new URL(config.endpoint); } catch { fail('Avatar asset endpoint is invalid.'); }
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
    fail('Avatar asset endpoint must be an HTTPS URL without credentials or a query.');
  }
  return config;
}

function validateManifest(manifest) {
  if (!object(manifest) || ![1, 2, 3].includes(manifest.schema_version)
    || manifest.delivery_review !== 'public_runtime_accepted'
    || !text(manifest.delivery_review_reference, 512)) fail('Avatar public runtime delivery has not been accepted.');
  const animated = manifest.schema_version >= 2;
  const wardrobe = manifest.schema_version === 3;
  const modelKeys = animated ? COSTUMES : ['archer'];
  if (!hasKeys(manifest.models, modelKeys)) fail('Avatar costume models are incomplete.');
  for (const model of Object.values(manifest.models)) {
    if (!object(model) || !filename(model.file, '.glb') || !Number.isFinite(model.rotation_y)
      || model.idle_clip !== (animated ? 'Idle' : null) || model.interaction_clips !== undefined
      || (model.clips !== undefined && (!Array.isArray(model.clips)
        || (animated ? model.clips.length !== 1 || model.clips[0] !== 'Idle' : model.clips.length)))) {
      fail('Avatar model contains an unreviewed capability.');
    }
    if (animated) {
      const evidence = model.animation_validation;
      if (!text(model.animation_review_reference, 512) || !SHA256.test(model.animation_source_sha256 ?? '')
        || !hasKeys(evidence, ['method', 'duration_seconds', 'sampled_frames', 'moving_vertices',
          'head_attachment_error', 'reimport_max_vertex_error', 'source_rest_joint_difference',
          'target_joint_error', 'rotation_delta_error', 'nonroot_translation_variation', 'source_scale_variation'])
        || evidence.method !== 'supplied-hierarchy-rotation-retarget-v1'
        || !Number.isFinite(evidence.duration_seconds) || evidence.duration_seconds <= 0 || evidence.duration_seconds > 60
        || !Number.isSafeInteger(evidence.sampled_frames) || evidence.sampled_frames < 3
        || !Number.isSafeInteger(evidence.moving_vertices) || evidence.moving_vertices < 1
        || !Number.isFinite(evidence.source_rest_joint_difference) || evidence.source_rest_joint_difference < 0
        || Object.entries({ head_attachment_error: 0.0001, reimport_max_vertex_error: 0.001,
          target_joint_error: 0.0001, rotation_delta_error: 0.0001,
          nonroot_translation_variation: 0.00001, source_scale_variation: 0.00001 }).some(([key, limit]) =>
          !Number.isFinite(evidence[key]) || evidence[key] < 0 || evidence[key] > limit)) {
        fail('Avatar supplied Idle conversion has not been verified and reviewed.');
      }
    }
  }
  const modelFiles = Object.values(manifest.models).map((model) => model.file);
  if (new Set(modelFiles).size !== modelFiles.length) fail('Avatar costumes must keep their complete matching models.');
  const parts = manifest.parts;
  if (!hasKeys(parts, ['body', 'head', 'face', 'hair', ...(wardrobe ? ['wardrobe'] : [])]) || !hasKeys(parts.hair, HAIR_STYLES)) {
    fail('Avatar mesh parts are incomplete.');
  }
  if (animated && !hasKeys(parts.head, HEADS)) fail('Avatar head choices are incomplete.');
  const heads = animated ? Object.values(parts.head) : [parts.head];
  const names = [parts.body, ...heads, parts.face, ...Object.values(parts.hair)];
  const wardrobeBindings = Object.create(null);
  if (wardrobe) {
    if (!hasKeys(parts.wardrobe, ['hair_for_hat', ...Object.keys(WARDROBE)])
      || Object.entries(WARDROBE).some(([slot, styles]) => !hasKeys(parts.wardrobe[slot], styles))) {
      fail('Avatar wardrobe modules are incomplete.');
    }
    names.push(parts.wardrobe.hair_for_hat, ...Object.keys(WARDROBE).flatMap((slot) => Object.values(parts.wardrobe[slot])));
    wardrobeBindings[parts.wardrobe.hair_for_hat] = 'RigHead';
    for (const [slot, bone] of Object.entries({ headwear: 'RigHead', mask: 'RigHead', bow: 'RigLPalm', quiver: 'RigRibcage' })) {
      for (const name of Object.values(parts.wardrobe[slot])) wardrobeBindings[name] = bone;
    }
  }
  // GLTFLoader uses these aliases as dictionary keys and sanitizes the
  // animation-binding delimiters. Preserve exact names through both paths.
  if (names.some((name) => !text(name, 128) || Object.hasOwn(Object.prototype, name) || /[[\].:/]/.test(name))
    || new Set(names).size !== names.length) fail('Avatar mesh parts must have distinct loader-safe names.');
  const textures = manifest.textures;
  const outfitKeys = animated ? COSTUMES.flatMap((style) => OUTFITS.map((outfit) => `${style}:${outfit}`)) : OUTFITS;
  const hairColors = animated ? EXPANDED_HAIR_COLORS : HAIR_COLORS;
  const faceKeys = animated ? FACES.flatMap((style) => hairColors.map((color) => `${style}:${color}`)) : hairColors;
  if (!hasKeys(textures, ['outfit', 'hair', 'face', ...(wardrobe ? ['wardrobe'] : [])]) || !hasKeys(textures.outfit, outfitKeys)
    || !hasKeys(textures.hair, hairColors) || !hasKeys(textures.face, faceKeys)
    || (wardrobe && !hasKeys(textures.wardrobe, WARDROBE_TEXTURE_KEYS))) fail('Avatar texture choices are incomplete.');
  const images = [...Object.values(textures.outfit), ...Object.values(textures.hair), ...Object.values(textures.face),
    ...(wardrobe ? Object.values(textures.wardrobe) : [])];
  if (images.some((name) => !filename(name, '.png')) || (!animated && new Set(images).size !== images.length)) fail('Avatar texture filenames are invalid.');
  return { models: manifest.models, names, inventory: [...modelFiles, ...new Set(images)], outfitKeys, hairColors, faceKeys, animated, wardrobe, wardrobeBindings };
}

function validatePng(bytes) {
  if (bytes.length < 45 || !bytes.subarray(0, 8).equals(PNG_SIGNATURE)) fail('Avatar image is not a bounded PNG.');
  let offset = 8;
  let hasData = false;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    if (!/^[A-Za-z]{4}$/.test(type) || length > bytes.length - offset - 12) fail('Avatar PNG structure is invalid.');
    if (offset === 8) {
      if (type !== 'IHDR' || length !== 13) fail('Avatar PNG header is invalid.');
      const width = bytes.readUInt32BE(offset + 8);
      const height = bytes.readUInt32BE(offset + 12);
      if (!width || !height || width > 2048 || height > 2048) fail('Avatar PNG dimensions exceed their limit.');
      if (![1, 2, 4, 8, 16].includes(bytes[offset + 16]) || ![0, 2, 3, 4, 6].includes(bytes[offset + 17])
        || bytes[offset + 18] !== 0 || bytes[offset + 19] !== 0 || bytes[offset + 20] > 1) fail('Avatar PNG format is invalid.');
    } else if (type === 'IHDR') fail('Avatar PNG has a duplicate header.');
    if (type === 'IDAT' && length > 0) hasData = true;
    offset += length + 12;
    if (type === 'IEND') {
      if (length !== 0 || offset !== bytes.length || !hasData) fail('Avatar PNG end is invalid.');
      return;
    }
  }
  fail('Avatar PNG is incomplete.');
}

function validateGlb(bytes, partNames, model, wardrobeBindings) {
  if (bytes.length < 28 || bytes.readUInt32LE(0) !== 0x46546c67 || bytes.readUInt32LE(4) !== 2
    || bytes.readUInt32LE(8) !== bytes.length) fail('Avatar GLB header is invalid.');
  const chunks = [];
  let offset = 12;
  while (offset < bytes.length) {
    if (offset + 8 > bytes.length) fail('Avatar GLB chunk header is incomplete.');
    const length = bytes.readUInt32LE(offset);
    const type = bytes.readUInt32LE(offset + 4);
    if (!length || length % 4 || length > bytes.length - offset - 8) fail('Avatar GLB chunk size is invalid.');
    chunks.push({ type, bytes: bytes.subarray(offset + 8, offset + 8 + length) });
    offset += length + 8;
  }
  if (chunks.length !== 2 || chunks[0].type !== 0x4e4f534a || chunks[1].type !== 0x004e4942) {
    fail('Avatar GLB must contain only JSON and embedded binary chunks.');
  }
  const document = parseJson(chunks[0].bytes, 'Avatar GLB JSON is invalid.');
  if (!object(document) || document.asset?.version !== '2.0'
    || ['extensionsUsed', 'extensionsRequired'].some((key) => document[key] !== undefined
      && (!Array.isArray(document[key]) || document[key].length))) fail('Avatar GLB contains unreviewed capabilities.');
  // The converter exports no extras. Runtime files cannot carry private
  // source/review metadata, URIs, extensions or scripts in embedded objects.
  const pending = [document];
  while (pending.length) {
    const entry = pending.pop();
    if (!entry || typeof entry !== 'object') continue;
    for (const [key, value] of Object.entries(entry)) {
      if (/^(uri|extensions|extras|scripts?)$/i.test(key)) fail('Avatar GLB contains an external or unreviewed reference.');
      if (value && typeof value === 'object') pending.push(value);
    }
  }
  const buffers = document.buffers;
  if (!Array.isArray(buffers) || buffers.length !== 1 || !Number.isSafeInteger(buffers[0]?.byteLength)
    || buffers[0].byteLength <= 0 || buffers[0].byteLength > chunks[1].bytes.length
    || chunks[1].bytes.length - buffers[0].byteLength > 3) fail('Avatar GLB embedded buffer is invalid.');
  const views = document.bufferViews;
  const accessors = document.accessors;
  if (!Array.isArray(views) || !views.length || !Array.isArray(accessors) || !accessors.length) fail('Avatar GLB geometry buffers are missing.');
  for (const view of views) {
    const start = view?.byteOffset ?? 0;
    if (!object(view) || view.buffer !== 0 || !Number.isSafeInteger(start) || start < 0
      || !Number.isSafeInteger(view.byteLength) || view.byteLength <= 0 || start + view.byteLength > buffers[0].byteLength
      || (view.byteStride !== undefined && (!Number.isSafeInteger(view.byteStride) || view.byteStride < 4
        || view.byteStride > 252 || view.byteStride % 4))) fail('Avatar GLB buffer view is invalid.');
  }
  const componentBytes = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
  const dimensions = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT2: 4, MAT3: 9, MAT4: 16 };
  for (const accessor of accessors) {
    if (!object(accessor) || !index(accessor.bufferView, views) || !Number.isInteger(accessor.componentType)
      || !Object.hasOwn(componentBytes, accessor.componentType)
      || !Object.hasOwn(dimensions, accessor.type) || !Number.isSafeInteger(accessor.count) || accessor.count <= 0
      || accessor.sparse !== undefined) fail('Avatar GLB accessor is invalid.');
    const view = views[accessor.bufferView];
    const componentSize = componentBytes[accessor.componentType];
    const columns = accessor.type.startsWith('MAT') ? Number(accessor.type.slice(3)) : 0;
    const size = columns ? Math.ceil(columns * componentSize / 4) * 4 * columns : componentSize * dimensions[accessor.type];
    const start = accessor.byteOffset ?? 0;
    const stride = view.byteStride ?? size;
    if (!Number.isSafeInteger(start) || start < 0 || (start + (view.byteOffset ?? 0)) % componentSize || stride < size
      || start + (accessor.count - 1) * stride + size > view.byteLength) fail('Avatar GLB accessor exceeds its buffer.');
  }
  const meshes = document.meshes;
  if (!Array.isArray(meshes) || !meshes.length) fail('Avatar GLB meshes are missing.');
  for (const mesh of meshes) {
    if (!Array.isArray(mesh?.primitives) || !mesh.primitives.length) fail('Avatar GLB mesh primitives are missing.');
    for (const primitive of mesh.primitives) {
      if (!object(primitive?.attributes) || !index(primitive.attributes.POSITION, accessors)
        || !index(primitive.attributes.TEXCOORD_0, accessors)
        || Object.values(primitive.attributes).some((value) => !index(value, accessors))
        || (primitive.mode ?? 4) !== 4 || (primitive.indices !== undefined && !index(primitive.indices, accessors))) {
        fail('Avatar GLB must contain triangle geometry with supplied UVs.');
      }
    }
  }
  for (const image of document.images ?? []) {
    if (!index(image?.bufferView, views) || !['image/png', 'image/jpeg'].includes(image.mimeType)) fail('Avatar GLB embedded image is invalid.');
  }
  const nodes = document.nodes;
  const scenes = document.scenes;
  if (!Array.isArray(nodes) || !Array.isArray(scenes) || !index(document.scene ?? 0, scenes)) fail('Avatar GLB scene is missing.');
  const skins = document.skins ?? [];
  if (!Array.isArray(skins)) fail('Avatar GLB skins are invalid.');
  for (const skin of skins) {
    if (!Array.isArray(skin?.joints) || !skin.joints.length || new Set(skin.joints).size !== skin.joints.length
      || skin.joints.some((joint) => !index(joint, nodes))
      || (skin.skeleton !== undefined && !index(skin.skeleton, nodes))
      || (skin.inverseBindMatrices !== undefined && (!index(skin.inverseBindMatrices, accessors)
        || accessors[skin.inverseBindMatrices].type !== 'MAT4' || accessors[skin.inverseBindMatrices].componentType !== 5126
        || accessors[skin.inverseBindMatrices].count < skin.joints.length))) fail('Avatar GLB skin references are invalid.');
  }
  const roots = scenes[document.scene ?? 0]?.nodes;
  if (!Array.isArray(roots) || !roots.length) fail('Avatar GLB scene nodes are missing.');
  const reachable = new Set();
  const queue = [...roots];
  while (queue.length) {
    const nodeIndex = queue.pop();
    if (!index(nodeIndex, nodes) || reachable.has(nodeIndex) || !object(nodes[nodeIndex])) fail('Avatar GLB scene graph is invalid.');
    reachable.add(nodeIndex);
    const node = nodes[nodeIndex];
    if (node.mesh !== undefined && !index(node.mesh, meshes)) fail('Avatar GLB mesh reference is invalid.');
    if (node.skin !== undefined && !index(node.skin, skins)) fail('Avatar GLB skin reference is invalid.');
    if (node.children !== undefined && !Array.isArray(node.children)) fail('Avatar GLB child references are invalid.');
    queue.push(...(node.children ?? []));
  }
  for (const name of partNames) {
    const matches = [...reachable].filter((nodeIndex) => nodes[nodeIndex].name === name);
    if (matches.length !== 1 || !index(nodes[matches[0]].mesh, meshes)) fail('Avatar GLB is missing a selected mesh part.');
  }
  if (Object.keys(wardrobeBindings).length && [...reachable].some((nodeIndex) =>
    nodes[nodeIndex].mesh !== undefined && !partNames.includes(nodes[nodeIndex].name))) {
    fail('Avatar wardrobe GLB contains undeclared mesh parts.');
  }
  validateIdle(document, chunks[1].bytes, reachable, model, partNames[0], wardrobeBindings);
}

function validateIdle(document, binary, reachable, model, bodyName, wardrobeBindings) {
  const animations = document.animations ?? [];
  if (!Array.isArray(animations)) fail('Avatar animation list is invalid.');
  if (model.idle_clip === null) {
    if (animations.length) fail('Static avatar GLB contains unreviewed animation.');
    return;
  }
  if (animations.length !== 1 || animations[0]?.name !== 'Idle') fail('Avatar GLB must contain only its reviewed Idle clip.');
  const animation = animations[0];
  const { accessors, bufferViews: views, nodes, meshes, skins = [] } = document;
  if (!skins.length || !Array.isArray(animation.samplers) || !animation.samplers.length
    || !Array.isArray(animation.channels) || !animation.channels.length) fail('Avatar Idle needs its matching rig and channels.');
  const body = [...reachable].map((nodeIndex) => nodes[nodeIndex]).find((node) => node.name === bodyName);
  if (!index(body?.skin, skins) || meshes[body.mesh].primitives.some((primitive) =>
    !index(primitive.attributes.JOINTS_0, accessors) || !index(primitive.attributes.WEIGHTS_0, accessors))) {
    fail('Avatar Idle needs a skinned body with supplied joint weights.');
  }
  const joints = new Set(skins[body.skin].joints);
  const requiredAttachments = new Map();
  for (const [name, bone] of Object.entries(wardrobeBindings)) {
    const matches = [...joints].filter((joint) => reachable.has(joint) && nodes[joint].name === bone);
    if (matches.length !== 1) fail('Avatar wardrobe needs its supplied attachment bones in the matching body rig.');
    requiredAttachments.set(name, matches[0]);
  }
  const contributingJoints = new Set();
  const targets = new Set();
  const usedSamplers = new Set();
  let movingJoint = false;
  let duration = 0;
  const values = (accessor, dimensions) => {
    const view = views[accessor.bufferView];
    const readers = { 5121: ['readUInt8', 1, 255], 5123: ['readUInt16LE', 2, 65535], 5126: ['readFloatLE', 4, 1] };
    const [reader, size, maximum] = readers[accessor.componentType];
    const stride = view.byteStride ?? dimensions * size;
    const start = (view.byteOffset ?? 0) + (accessor.byteOffset ?? 0);
    return Array.from({ length: accessor.count }, (_, entry) => Array.from({ length: dimensions }, (_, component) =>
      binary[reader](start + entry * stride + component * size) / (accessor.normalized ? maximum : 1)));
  };
  const validateSkinAttributes = (skinned) => {
    if (!index(skinned.mesh, meshes)) fail('Avatar skinned node must contain its matching mesh.');
    const skinJoints = skins[skinned.skin].joints;
    for (const primitive of meshes[skinned.mesh].primitives) {
      const position = accessors[primitive.attributes.POSITION];
      if (position.type !== 'VEC3' || position.componentType !== 5126
        || Object.keys(primitive.attributes).some((key) => /^(JOINTS|WEIGHTS)_/.test(key) && !/^(JOINTS|WEIGHTS)_[01]$/.test(key))) {
        fail('Avatar body joint and weight attributes are invalid.');
      }
      const sets = [0];
      if (primitive.attributes.JOINTS_1 !== undefined || primitive.attributes.WEIGHTS_1 !== undefined) sets.push(1);
      const influences = sets.map((set) => {
        const joint = accessors[primitive.attributes[`JOINTS_${set}`]];
        const weight = accessors[primitive.attributes[`WEIGHTS_${set}`]];
        if (!joint || !weight
          || joint.type !== 'VEC4' || ![5121, 5123].includes(joint.componentType)
          || (joint.normalized !== undefined && joint.normalized !== false) || joint.count !== position.count
          || weight.type !== 'VEC4' || ![5121, 5123, 5126].includes(weight.componentType) || weight.count !== position.count
          // GLTFLoader normalizes set0 in its original storage. Quantized
          // paired weights can round away the total needed by our restoration.
          || (sets.length > 1 && weight.componentType !== 5126)
          || (weight.componentType === 5126
            ? weight.normalized !== undefined && weight.normalized !== false : weight.normalized !== true)) {
          fail('Avatar body requires paired valid joint and weight attributes.');
        }
        return { joints: values(joint, 4), weights: values(weight, 4) };
      });
      for (let vertex = 0; vertex < position.count; vertex++) {
        let totalWeight = 0;
        for (const influence of influences) {
          const weights = influence.weights[vertex];
          const jointValues = influence.joints[vertex];
          if (jointValues.some((value) => !index(value, skinJoints))
            || weights.some((value) => !Number.isFinite(value) || value < 0 || value > 1)) {
            fail('Avatar body requires finite normalized weights on valid joints.');
          }
          totalWeight += weights.reduce((sum, value) => sum + value, 0);
          for (let component = 0; component < 4; component++) {
            if (skinned === body && weights[component] > 0) contributingJoints.add(skinJoints[jointValues[component]]);
            if (requiredAttachments.has(skinned.name) && weights[component] > 0
              && skinJoints[jointValues[component]] !== requiredAttachments.get(skinned.name)) {
              fail('Avatar wardrobe weights must preserve their supplied rigid attachment bone.');
            }
          }
        }
        // Preserve up to eight supplied influences. Normalizing the first four
        // alone discards the fifth weight present on the publisher's Archer03.
        const tolerance = sets.length === 2 ? 0.000001 : 0.001;
        if (Math.abs(totalWeight - 1) > tolerance) fail('Avatar body combined weights must be normalized.');
      }
    }
  };
  for (const nodeIndex of reachable) {
    const node = nodes[nodeIndex];
    if (node.skin !== undefined) validateSkinAttributes(node);
  }
  // An animated ancestor deforms a descendant's weighted vertices too. Merely
  // moving an unrelated, unweighted bone is not body animation.
  const parents = new Map();
  for (const nodeIndex of reachable) {
    for (const child of nodes[nodeIndex].children ?? []) parents.set(child, nodeIndex);
  }
  for (const nodeIndex of reachable) {
    const node = nodes[nodeIndex];
    if (!requiredAttachments.has(node.name) || node.skin !== undefined) continue;
    let ancestor = parents.get(nodeIndex);
    while (ancestor !== undefined && !joints.has(ancestor)) ancestor = parents.get(ancestor);
    if (ancestor !== requiredAttachments.get(node.name)) fail('Avatar wardrobe must follow its supplied attachment bone.');
  }
  for (const nodeIndex of [...contributingJoints]) {
    let ancestor = parents.get(nodeIndex);
    while (ancestor !== undefined) {
      contributingJoints.add(ancestor);
      ancestor = parents.get(ancestor);
    }
  }
  for (const channel of animation.channels) {
    if (!index(channel?.sampler, animation.samplers) || !reachable.has(channel?.target?.node)
      || !['translation', 'rotation', 'scale'].includes(channel.target.path)) fail('Avatar Idle channel target is invalid.');
    const target = `${channel.target.node}:${channel.target.path}`;
    if (targets.has(target)) fail('Avatar Idle has duplicate channel targets.');
    targets.add(target);
    usedSamplers.add(channel.sampler);
    const sampler = animation.samplers[channel.sampler];
    if (!index(sampler?.input, accessors) || !index(sampler?.output, accessors)
      || !['LINEAR', 'STEP'].includes(sampler.interpolation ?? 'LINEAR')) fail('Avatar Idle sampler is invalid.');
    const input = accessors[sampler.input];
    const output = accessors[sampler.output];
    const dimensions = channel.target.path === 'rotation' ? 4 : 3;
    if (input.type !== 'SCALAR' || input.componentType !== 5126 || input.count < 2
      || output.componentType !== 5126 || output.type !== `VEC${dimensions}` || output.count !== input.count) {
      fail('Avatar Idle keyframes are invalid.');
    }
    const times = values(input, 1).map(([time]) => time);
    if (times.some((time, entry) => !Number.isFinite(time) || time < 0 || (entry > 0 && time <= times[entry - 1]))
      || times.at(-1) <= times[0] || times.at(-1) > 60) fail('Avatar Idle timing is invalid.');
    duration = Math.max(duration, times.at(-1));
    const samples = values(output, dimensions);
    if (samples.some((sample) => sample.some((value) => !Number.isFinite(value))
      || (channel.target.path === 'rotation' && Math.abs(Math.hypot(...sample) - 1) > 0.01)
      || (channel.target.path === 'scale' && sample.some((value) => value <= 0)))) fail('Avatar Idle transforms are invalid.');
    const changed = (sample) => {
      if (channel.target.path !== 'rotation') {
        return sample.some((value, component) => Math.abs(value - samples[0][component]) > 0.000001);
      }
      // q and -q represent the same orientation. Normalize before comparing
      // so harmless quaternion length rounding cannot claim physical motion.
      const first = samples[0].map((value) => value / Math.hypot(...samples[0]));
      const normalized = sample.map((value) => value / Math.hypot(...sample));
      const sign = first.reduce((dot, value, component) => dot + value * normalized[component], 0) < 0 ? -1 : 1;
      return normalized.some((value, component) => Math.abs(sign * value - first[component]) > 0.000001);
    };
    if (joints.has(channel.target.node) && contributingJoints.has(channel.target.node) && samples.some(changed)) {
      movingJoint = true;
    }
  }
  if (usedSamplers.size !== animation.samplers.length || !movingJoint) fail('Avatar Idle must animate its supplied skeleton.');
  if (Math.abs(duration - model.animation_validation.duration_seconds) > 0.001) {
    fail('Avatar Idle duration differs from its measured conversion evidence.');
  }
}

export function validateAvatarBundle(bytes, expectedHash) {
  if (typeof expectedHash !== 'string' || !SHA256.test(expectedHash)) fail('ABBY_AVATAR_ASSETS_SHA256 must be a SHA-256 digest.');
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > MAX_BUNDLE_BYTES) fail('Avatar asset artifact size is invalid.');
  if (hash(bytes) !== expectedHash) fail('Avatar asset artifact digest does not match.');
  const bundle = parseJson(bytes, 'Avatar asset artifact JSON is invalid.');
  if (!hasKeys(bundle, ['schema_version', 'manifest', 'files']) || bundle.schema_version !== 1) fail('Avatar asset artifact schema is invalid.');
  const { models, names, inventory, outfitKeys, hairColors, faceKeys, wardrobe, wardrobeBindings } = validateManifest(bundle.manifest);
  if (!hasKeys(bundle.files, inventory)) fail('Avatar asset inventory differs from the accepted runtime files.');
  const files = new Map();
  for (const [name, file] of Object.entries(bundle.files)) {
    if (!hasKeys(file, ['sha256', 'base64']) || typeof file.sha256 !== 'string' || !SHA256.test(file.sha256)
      || typeof file.base64 !== 'string' || file.base64.length > Math.ceil(MAX_FILE_BYTES / 3) * 4 || !BASE64.test(file.base64)) {
      fail('Avatar asset file encoding is invalid.');
    }
    const content = Buffer.from(file.base64, 'base64');
    if (!content.length || content.length > MAX_FILE_BYTES || content.toString('base64') !== file.base64
      || hash(content) !== file.sha256) fail('Avatar asset file digest or size is invalid.');
    const model = Object.values(models).find((entry) => entry.file === name);
    if (model) validateGlb(content, names, model, wardrobeBindings);
    else validatePng(content);
    files.set(name, content);
  }
  // Export reports and acceptance evidence can contain private source details.
  // Vite imports this document eagerly, so stage only the renderer's contract.
  const select = (value, keys) => Object.fromEntries(keys.map((key) => [key, value[key]]));
  const manifest = {
    schema_version: bundle.manifest.schema_version,
    models: Object.fromEntries(Object.entries(models).map(([key, model]) => [key, select(model, ['file', 'idle_clip', 'rotation_y'])])),
    parts: { ...select(bundle.manifest.parts, ['body', 'head', 'face']), hair: select(bundle.manifest.parts.hair, HAIR_STYLES) },
    textures: {
      outfit: select(bundle.manifest.textures.outfit, outfitKeys),
      hair: select(bundle.manifest.textures.hair, hairColors),
      face: select(bundle.manifest.textures.face, faceKeys),
    },
  };
  if (wardrobe) {
    manifest.parts.wardrobe = {
      hair_for_hat: bundle.manifest.parts.wardrobe.hair_for_hat,
      ...Object.fromEntries(Object.entries(WARDROBE).map(([slot, styles]) => [slot, select(bundle.manifest.parts.wardrobe[slot], styles)])),
    };
    manifest.textures.wardrobe = select(bundle.manifest.textures.wardrobe, WARDROBE_TEXTURE_KEYS);
  }
  return { manifest, files };
}

export async function stageAvatarArt({
  secretPath = '/run/secrets/ABBY_AVATAR_ASSETS',
  expectedHash = process.env.ABBY_AVATAR_ASSETS_SHA256,
  required = process.env.ABBY_AVATAR_ASSETS_REQUIRED === 'true',
  destination = join(frontendRoot, 'src', 'avatar', 'licensed'),
  download = downloadArtifact,
} = {}) {
  const secretDirectory = dirname(secretPath);
  const requiredSecret = await readOptionalSecret(join(secretDirectory, 'ABBY_AVATAR_ASSETS_REQUIRED'));
  if (requiredSecret) {
    const value = requiredSecret.toString('utf8').trim();
    if (!['true', 'false'].includes(value)) fail('Avatar asset required flag is invalid.');
    required ||= value === 'true';
  }
  const secret = await readOptionalSecret(secretPath);
  if (!secret) {
    if (required) fail('Required avatar asset build secret is missing.');
    return { staged: false, fileCount: 0 };
  }
  if (!expectedHash) expectedHash = (await readOptionalSecret(join(secretDirectory, 'ABBY_AVATAR_ASSETS_SHA256')))?.toString('utf8').trim();
  if (typeof expectedHash !== 'string' || !SHA256.test(expectedHash)) fail('ABBY_AVATAR_ASSETS_SHA256 must be a SHA-256 digest.');
  const config = validateConfig(parseJson(secret, 'Avatar asset secret JSON is invalid.'));
  const { manifest, files } = validateAvatarBundle(await download(config), expectedHash);
  const target = resolve(destination);
  try {
    await lstat(target);
    fail('Refusing to replace an existing avatar staging directory.');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const parent = dirname(target);
  await mkdir(parent, { recursive: true });
  const temporary = await mkdtemp(join(parent, '.avatar-staging-'));
  try {
    for (const [name, content] of files) await writeFile(join(temporary, name), content, { mode: 0o600 });
    await writeFile(join(temporary, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', { mode: 0o600 });
    await rename(temporary, target);
  } catch (error) {
    if (dirname(resolve(temporary)) === parent && basename(temporary).startsWith('.avatar-staging-')) {
      await rm(temporary, { recursive: true, force: true });
    }
    throw error;
  }
  return { staged: true, fileCount: files.size };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = await stageAvatarArt();
    process.stdout.write(result.staged ? `Staged ${result.fileCount} accepted avatar runtime files.\n` : 'No avatar art secret supplied; using the public preview fallback.\n');
  } catch {
    // Never expose SDK/config errors, private paths, credentials or artwork.
    process.stderr.write('Avatar art staging failed. Check the accepted private object, expected digest and build secret configuration.\n');
    process.exitCode = 1;
  }
}

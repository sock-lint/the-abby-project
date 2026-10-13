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
  if (!object(manifest) || manifest.schema_version !== 1
    || manifest.delivery_review !== 'public_runtime_accepted'
    || !text(manifest.delivery_review_reference, 512)) fail('Avatar public runtime delivery has not been accepted.');
  const model = manifest.models?.archer;
  if (!hasKeys(manifest.models, ['archer']) || !object(model) || !filename(model.file, '.glb')
    || model.idle_clip !== null || !Number.isFinite(model.rotation_y)
    || (model.clips !== undefined && (!Array.isArray(model.clips) || model.clips.length))
    || model.interaction_clips !== undefined) fail('Avatar model must be the accepted static Archer.');
  const parts = manifest.parts;
  if (!hasKeys(parts, ['body', 'head', 'face', 'hair']) || !hasKeys(parts.hair, HAIR_STYLES)) {
    fail('Avatar mesh parts are incomplete.');
  }
  const names = [parts.body, parts.head, parts.face, ...Object.values(parts.hair)];
  if (names.some((name) => !text(name, 128)) || new Set(names).size !== names.length) fail('Avatar mesh parts must have distinct names.');
  const textures = manifest.textures;
  if (!hasKeys(textures, ['outfit', 'hair', 'face']) || !hasKeys(textures.outfit, OUTFITS)
    || !hasKeys(textures.hair, HAIR_COLORS) || !hasKeys(textures.face, HAIR_COLORS)) fail('Avatar texture choices are incomplete.');
  const images = [...Object.values(textures.outfit), ...Object.values(textures.hair), ...Object.values(textures.face)];
  if (images.some((name) => !filename(name, '.png')) || new Set(images).size !== images.length) fail('Avatar texture filenames are invalid.');
  return { model, names, inventory: [model.file, ...images] };
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

function validateGlb(bytes, partNames) {
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
    || ['extensionsUsed', 'extensionsRequired', 'animations'].some((key) => document[key] !== undefined
      && (!Array.isArray(document[key]) || document[key].length))) fail('Avatar GLB contains unreviewed capabilities.');
  // No URI, extension or script can hide in an embedded material or extras.
  const pending = [document];
  while (pending.length) {
    const entry = pending.pop();
    if (!entry || typeof entry !== 'object') continue;
    for (const [key, value] of Object.entries(entry)) {
      if (/^(uri|extensions|scripts?)$/i.test(key)) fail('Avatar GLB contains an external or unreviewed reference.');
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
}

export function validateAvatarBundle(bytes, expectedHash) {
  if (typeof expectedHash !== 'string' || !SHA256.test(expectedHash)) fail('ABBY_AVATAR_ASSETS_SHA256 must be a SHA-256 digest.');
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > MAX_BUNDLE_BYTES) fail('Avatar asset artifact size is invalid.');
  if (hash(bytes) !== expectedHash) fail('Avatar asset artifact digest does not match.');
  const bundle = parseJson(bytes, 'Avatar asset artifact JSON is invalid.');
  if (!hasKeys(bundle, ['schema_version', 'manifest', 'files']) || bundle.schema_version !== 1) fail('Avatar asset artifact schema is invalid.');
  const { model, names, inventory } = validateManifest(bundle.manifest);
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
    if (name === model.file) validateGlb(content, names);
    else validatePng(content);
    files.set(name, content);
  }
  // Export reports and acceptance evidence can contain private source details.
  // Vite imports this document eagerly, so stage only the renderer's contract.
  const select = (value, keys) => Object.fromEntries(keys.map((key) => [key, value[key]]));
  const manifest = {
    schema_version: 1,
    models: { archer: { file: model.file, idle_clip: null, rotation_y: model.rotation_y } },
    parts: { ...select(bundle.manifest.parts, ['body', 'head', 'face']), hair: select(bundle.manifest.parts.hair, HAIR_STYLES) },
    textures: {
      outfit: select(bundle.manifest.textures.outfit, OUTFITS),
      hair: select(bundle.manifest.textures.hair, HAIR_COLORS),
      face: select(bundle.manifest.textures.face, HAIR_COLORS),
    },
  };
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

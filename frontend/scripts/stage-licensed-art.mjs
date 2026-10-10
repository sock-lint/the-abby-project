import { createHash } from 'node:crypto';
import { lstat, mkdir, mkdtemp, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { isDeepStrictEqual } from 'node:util';
import { GetObjectCommand, S3Client } from '@aws-sdk/client-s3';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const MAX_CONFIG_BYTES = 16 * 1024;
const MAX_BUNDLE_BYTES = 8 * 1024 * 1024;
const MAX_IMAGE_BYTES = 2 * 1024 * 1024;
const PNG_SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
const SHA256 = /^[a-f0-9]{64}$/;
const PNG_NAME = /^[a-z][a-z0-9_-]{0,63}\.png$/;

async function readOptionalSecret(path) {
  try {
    const metadata = await lstat(path);
    if (!metadata.isFile() || metadata.size > MAX_CONFIG_BYTES) fail('Licensed asset secret size is invalid.');
    return await readFile(path);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    return undefined;
  }
}

function fail(message) {
  throw new Error(message);
}

function parseJson(bytes, message) {
  try { return JSON.parse(bytes.toString('utf8')); } catch { fail(message); }
}

function hasKeys(value, keys) {
  return value && typeof value === 'object' && !Array.isArray(value)
    && isDeepStrictEqual(Object.keys(value).sort(), [...keys].sort());
}

function validateConfig(config) {
  const keys = ['endpoint', 'bucket', 'key', 'region', 'accessKeyId', 'secretAccessKey'];
  if (!hasKeys(config, keys) || keys.some((key) => typeof config[key] !== 'string' || !config[key].trim())) {
    fail('Licensed asset secret configuration is invalid.');
  }
  let endpoint;
  try { endpoint = new URL(config.endpoint); } catch { fail('Licensed asset endpoint is invalid.'); }
  if (endpoint.protocol !== 'https:' || endpoint.username || endpoint.password || endpoint.search || endpoint.hash) {
    fail('Licensed asset endpoint must be an HTTPS URL without credentials or a query.');
  }
  return config;
}

export async function downloadArtifact(config, client = new S3Client({
  endpoint: config.endpoint,
  region: config.region,
  forcePathStyle: true,
  maxAttempts: 2,
  credentials: { accessKeyId: config.accessKeyId, secretAccessKey: config.secretAccessKey },
})) {
  try {
    const response = await client.send(new GetObjectCommand({ Bucket: config.bucket, Key: config.key }), {
      abortSignal: AbortSignal.timeout(30_000),
    });
    if (!response.Body || response.ContentLength > MAX_BUNDLE_BYTES) fail('Invalid artifact response.');
    const chunks = [];
    let size = 0;
    for await (const chunk of response.Body) {
      const bytes = Buffer.from(chunk);
      size += bytes.length;
      if (size > MAX_BUNDLE_BYTES) fail('Artifact exceeds its size limit.');
      chunks.push(bytes);
    }
    if (!size) fail('Artifact is empty.');
    return Buffer.concat(chunks);
  } catch {
    // SDK errors can contain endpoint/request details. Never print them or the
    // secret document to build logs.
    fail('Private licensed asset download failed. Check the build secret and private object.');
  } finally {
    client.destroy?.();
  }
}

function validatePng(bytes) {
  if (bytes.length < 45 || bytes.length > MAX_IMAGE_BYTES || !bytes.subarray(0, 8).equals(PNG_SIGNATURE)) {
    fail('Licensed image is not a bounded PNG.');
  }
  let offset = 8;
  let hasData = false;
  let hasEnd = false;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    if (!/^[A-Za-z]{4}$/.test(type) || length > bytes.length - offset - 12) fail('Licensed PNG structure is invalid.');
    if (offset === 8) {
      if (type !== 'IHDR' || length !== 13) fail('Licensed PNG header is invalid.');
      const width = bytes.readUInt32BE(offset + 8);
      const height = bytes.readUInt32BE(offset + 12);
      if (!width || !height || width > 2048 || height > 2048) fail('Licensed PNG dimensions exceed their limit.');
      if (![1, 2, 4, 8, 16].includes(bytes[offset + 16]) || ![0, 2, 3, 4, 6].includes(bytes[offset + 17])
        || bytes[offset + 18] !== 0 || bytes[offset + 19] !== 0 || bytes[offset + 20] > 1) {
        fail('Licensed PNG format is invalid.');
      }
    } else if (type === 'IHDR') fail('Licensed PNG has a duplicate header.');
    if (type === 'IDAT' && length > 0) hasData = true;
    offset += length + 12;
    if (type === 'IEND') {
      if (length !== 0 || offset !== bytes.length) fail('Licensed PNG end is invalid.');
      hasEnd = true;
      break;
    }
  }
  if (!hasData || !hasEnd) fail('Licensed PNG is incomplete.');
}

export function validateBundle(bytes, expectedHash, baseline) {
  if (!SHA256.test(expectedHash || '')) fail('ABBY_MEADOW_ASSETS_SHA256 must be a SHA-256 digest.');
  if (!Buffer.isBuffer(bytes) || !bytes.length || bytes.length > MAX_BUNDLE_BYTES) fail('Licensed asset artifact size is invalid.');
  if (createHash('sha256').update(bytes).digest('hex') !== expectedHash) fail('Licensed asset artifact digest does not match.');
  const bundle = parseJson(bytes, 'Licensed asset artifact JSON is invalid.');
  if (!hasKeys(bundle, ['schema_version', 'presentation', 'images']) || bundle.schema_version !== 1) {
    fail('Licensed asset artifact schema is invalid.');
  }
  const presentation = bundle.presentation;
  if (!hasKeys(presentation, ['schema_version', 'palette', 'typography', 'companion', 'keepsakes'])
    || presentation.schema_version !== baseline.schema_version
    || !['palette', 'typography', 'keepsakes'].every((key) => isDeepStrictEqual(presentation[key], baseline[key]))) {
    fail('Licensed presentation is incompatible with the public presentation.');
  }
  const companion = presentation.companion;
  if (!hasKeys(companion, ['id', 'label', 'art_key', 'temporary', 'portrait', 'happy_portrait', 'blink_portrait'])
    || companion.id !== baseline.companion.id || companion.temporary !== false
    || typeof companion.label !== 'string' || !companion.label.trim() || companion.label.length > 80
    || [...companion.label].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127)
    || typeof companion.art_key !== 'string' || !/^[a-z][a-z0-9_-]{0,63}$/.test(companion.art_key)) {
    fail('Licensed companion presentation is invalid.');
  }
  if (!bundle.images || typeof bundle.images !== 'object' || Array.isArray(bundle.images)) fail('Licensed image map is invalid.');
  const entries = Object.entries(bundle.images);
  if (!entries.length || entries.length > 8) fail('Licensed image count is invalid.');
  const images = new Map();
  for (const [name, image] of entries) {
    if (!PNG_NAME.test(name) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])\.png$/.test(name)) fail('Licensed image filename is unsafe.');
    if (!hasKeys(image, ['sha256', 'base64']) || !SHA256.test(image.sha256 || '')
      || typeof image.base64 !== 'string' || image.base64.length > Math.ceil(MAX_IMAGE_BYTES / 3) * 4
      || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(image.base64)) {
      fail('Licensed image encoding is invalid.');
    }
    const imageBytes = Buffer.from(image.base64, 'base64');
    if (imageBytes.toString('base64') !== image.base64
      || createHash('sha256').update(imageBytes).digest('hex') !== image.sha256) fail('Licensed image digest does not match.');
    validatePng(imageBytes);
    images.set(name, imageBytes);
  }
  if (!['portrait', 'happy_portrait', 'blink_portrait'].every((key) => images.has(companion[key]))) {
    fail('Licensed companion portrait is missing from the artifact.');
  }
  return { presentation, images };
}

export async function stageLicensedArt({
  secretPath = '/run/secrets/ABBY_MEADOW_ASSETS',
  expectedHash = process.env.ABBY_MEADOW_ASSETS_SHA256,
  required = process.env.ABBY_MEADOW_ASSETS_REQUIRED === 'true',
  releasePath = join(frontendRoot, 'scripts', 'meadow-art.release.json'),
  destination = join(frontendRoot, 'src', 'storybook', 'licensed'),
  baselinePath = join(frontendRoot, 'src', 'storybook', 'presentation.json'),
  download = downloadArtifact,
} = {}) {
  const secretDirectory = dirname(secretPath);
  const requiredSecret = await readOptionalSecret(join(secretDirectory, 'ABBY_MEADOW_ASSETS_REQUIRED'));
  if (requiredSecret) {
    const value = requiredSecret.toString('utf8').trim();
    if (!['true', 'false'].includes(value)) fail('Licensed asset required flag is invalid.');
    required ||= value === 'true';
  }
  const secret = await readOptionalSecret(secretPath);
  const awsNames = ['AWS_S3_ENDPOINT_URL', 'AWS_STORAGE_BUCKET_NAME', 'AWS_S3_REGION_NAME', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'];
  const awsSecrets = secret ? [] : await Promise.all(awsNames.map((name) => readOptionalSecret(join(secretDirectory, name))));
  if (!secret && !awsSecrets.some(Boolean)) {
    if (required) fail('Required licensed asset build secret is missing.');
    return { staged: false, imageCount: 0 };
  }
  const release = parseJson(await readFile(releasePath), 'Licensed asset release pointer JSON is invalid.');
  if (!hasKeys(release, ['key', 'sha256']) || typeof release.key !== 'string' || !release.key.trim()
    || release.key.length > 512 || !SHA256.test(release.sha256 || '')) fail('Licensed asset release pointer is invalid.');
  expectedHash ||= release.sha256;
  if (!SHA256.test(expectedHash || '')) fail('ABBY_MEADOW_ASSETS_SHA256 must be a SHA-256 digest.');
  const [endpoint, bucket, region, accessKeyId, secretAccessKey] = awsSecrets.map((value) => value?.toString('utf8').trim());
  const config = validateConfig(secret ? parseJson(secret, 'Licensed asset secret JSON is invalid.') : {
    endpoint, bucket, key: release.key, region: region || 'us-east-1', accessKeyId, secretAccessKey,
  });
  const baseline = parseJson(await readFile(baselinePath), 'Public presentation JSON is invalid.');
  const bundle = validateBundle(await download(config), expectedHash, baseline);
  const target = resolve(destination);
  try {
    await lstat(target);
    fail('Refusing to replace an existing licensed staging directory.');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const parent = dirname(target);
  await mkdir(parent, { recursive: true });
  const temporary = await mkdtemp(join(parent, '.licensed-staging-'));
  try {
    for (const [name, bytes] of bundle.images) await writeFile(join(temporary, name), bytes, { mode: 0o600 });
    await writeFile(join(temporary, 'presentation.json'), JSON.stringify(bundle.presentation, null, 2) + '\n', { mode: 0o600 });
    await rename(temporary, target);
  } catch (error) {
    // The absolute generated path must stay beneath the intended parent before
    // recursive cleanup on Windows or Linux.
    if (dirname(resolve(temporary)) === parent && basename(temporary).startsWith('.licensed-staging-')) {
      await rm(temporary, { recursive: true, force: true });
    }
    throw error;
  }
  return { staged: true, imageCount: bundle.images.size };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = await stageLicensedArt();
    process.stdout.write(result.staged ? `Staged ${result.imageCount} licensed companion portraits.\n` : 'No licensed art secret supplied; using public presentation.\n');
  } catch {
    // Never expose SDK/config errors, file paths, secrets, or artifact content.
    process.stderr.write('Licensed art staging failed. Check the private object, expected digest and build secret configuration.\n');
    process.exitCode = 1;
  }
}

import { createHash, randomUUID } from 'node:crypto';
import { lstat, mkdir, open, readFile, readdir, rename, rm, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import yauzl from 'yauzl';

const policyPath = new URL('../../shared/catalog/companion-supplemental.json', import.meta.url);
const policy = JSON.parse(await readFile(policyPath, 'utf8'));
const marker = '.abby-companion-supplementals.json';
const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
const safe = (name) => typeof name === 'string' && name && !/[\\:\0]/.test(name)
  && !name.startsWith('/') && name.split('/').every((part) => part && part !== '.' && part !== '..');
const exists = async (path) => { try { await lstat(path); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; } };

async function plainFile(root, relative) {
  if (!safe(relative)) throw new Error('Unsafe supplemental path');
  let path = resolve(root);
  if (!(await lstat(path)).isDirectory() || (await lstat(path)).isSymbolicLink()) throw new Error('Supplemental source must be a plain directory');
  for (const part of relative.split('/')) {
    path = join(path, part);
    if ((await lstat(path)).isSymbolicLink()) throw new Error('Supplemental sources cannot contain links');
  }
  if (!(await lstat(path)).isFile()) throw new Error('Supplemental source must be a regular file');
  return path;
}

async function checkedBytes(source, record) {
  const bytes = await readFile(source);
  if (bytes.length !== record.bytes || digest(bytes) !== record.sha256) throw new Error(`Supplemental integrity mismatch: ${record.path || record.filename}`);
  return bytes;
}

async function destinationState(destination, definition) {
  if (!await exists(destination)) return null;
  const directory = await lstat(destination);
  if (!directory.isDirectory() || directory.isSymbolicLink() || !await exists(join(destination, marker))) throw new Error('Refusing to replace an unmanaged supplemental directory');
  const allowed = new Set([marker, ...definition.files.map((file) => file.filename)]);
  const names = (await readdir(destination)).sort(), files = [];
  if (names.some((name) => !allowed.has(name))) throw new Error('Refusing to replace unknown supplemental files');
  for (const name of names) {
    const path = await plainFile(destination, name), stat = await lstat(path);
    if (stat.size > 16 * 1024 ** 2) throw new Error('Refusing to replace an unmanaged supplemental file');
    files.push([name, stat.dev, stat.ino, stat.size, digest(await readFile(path))]);
  }
  return JSON.stringify([directory.dev, directory.ino, files]);
}

export async function verifySupplementals(destination, definition = policy) {
  const receipt = JSON.parse(await readFile(await plainFile(destination, marker), 'utf8'));
  if (receipt.index_sha256 !== definition.index_sha256 || receipt.inventory_sha256 !== definition.inventory_sha256) throw new Error('Supplemental receipt does not match the pinned delivery');
  const expected = [marker, ...definition.files.map((file) => file.filename)].sort();
  const actual = (await readdir(destination)).sort();
  if (JSON.stringify(actual) !== JSON.stringify(expected)) throw new Error('Supplemental tree contains missing or unexpected files');
  for (const file of definition.files) await checkedBytes(await plainFile(destination, file.filename), file);
  return { files: definition.files.length, verified: true };
}

async function bufferStream(stream, limit) {
  const chunks = []; let bytes = 0;
  try {
    for await (const chunk of stream) {
      bytes += chunk.length;
      if (bytes > limit) throw new Error('Supplemental input exceeds its verified size bound');
      chunks.push(chunk);
    }
    return Buffer.concat(chunks, bytes);
  } finally { stream.destroy?.(); }
}

// Every file is checked against the inventory before any handoff or selected
// image is used. Entries remain in memory; archive paths never reach disk.
export async function verifyWorkspaceZip(bytes, definition = policy) {
  const zip = await new Promise((accept, reject) => yauzl.fromBuffer(bytes,
    { autoClose: false, lazyEntries: true, strictFileNames: true, validateEntrySizes: true }, (error, value) => error ? reject(error) : accept(value)));
  const entries = new Map(); let total = 0;
  try {
    await new Promise((accept, reject) => {
      zip.on('error', reject);
      zip.on('end', accept);
      zip.on('entry', (entry) => {
        try {
          const name = entry.fileName.replace(/\/$/, '');
          if (!safe(name) || entries.has(name) || ((entry.externalFileAttributes >>> 16) & 0o170000) === 0o120000) throw new Error('Unsafe or duplicate workspace archive entry');
          total += entry.uncompressedSize;
          if (entries.size >= 20_000 || total > 2 * 1024 ** 3 || entry.uncompressedSize > 512 * 1024 ** 2) throw new Error('Workspace archive exceeds its bounds');
          entries.set(name, entry); zip.readEntry();
        } catch (error) { reject(error); }
      });
      zip.readEntry();
    });
    const read = async (name) => {
      const entry = entries.get(name);
      if (!entry || entry.fileName.endsWith('/')) throw new Error(`Workspace file missing: ${name}`);
      const stream = await new Promise((accept, reject) => zip.openReadStream(entry, (error, value) => error ? reject(error) : accept(value)));
      return bufferStream(stream, entry.uncompressedSize);
    };
    const inventoryBytes = await read('inventory.json');
    if (digest(inventoryBytes) !== definition.inventory_sha256) throw new Error('Workspace inventory digest mismatch');
    const inventory = JSON.parse(inventoryBytes);
    if (JSON.stringify(inventory.pin) !== JSON.stringify(definition.pin) || !Array.isArray(inventory.files)) throw new Error('Workspace pin mismatch');
    const expected = new Set(['inventory.json']); const selected = new Map();
    for (const file of inventory.files) {
      if (!safe(file.path) || expected.has(file.path)) throw new Error('Invalid workspace inventory path');
      expected.add(file.path);
      const content = await read(file.path);
      if (content.length !== file.bytes || digest(content) !== file.sha256) throw new Error(`Workspace inventory mismatch: ${file.path}`);
      const image = definition.files.find((item) => item.path === file.path);
      if (image) {
        if (file.sha256 !== image.sha256 || file.bytes !== image.bytes) throw new Error('Supplemental declaration mismatch');
        selected.set(image.filename, content);
      }
    }
    for (const [name, entry] of entries) if (!entry.fileName.endsWith('/') && !expected.has(name)) throw new Error('Unexpected workspace file');
    if (selected.size !== definition.files.length) throw new Error('Workspace supplemental image is missing');
    return selected;
  } finally { zip.close(); }
}

async function localImages(workspace, definition) {
  const inventoryBytes = await readFile(await plainFile(workspace, 'inventory.json'));
  if (digest(inventoryBytes) !== definition.inventory_sha256) throw new Error('Workspace inventory digest mismatch');
  const inventory = JSON.parse(inventoryBytes);
  if (JSON.stringify(inventory.pin) !== JSON.stringify(definition.pin)) throw new Error('Workspace pin mismatch');
  const selected = new Map();
  for (const file of inventory.files) {
    const bytes = await checkedBytes(await plainFile(workspace, file.path), file);
    const image = definition.files.find((item) => item.path === file.path);
    if (image) {
      if (image.sha256 !== file.sha256 || image.bytes !== file.bytes) throw new Error('Supplemental declaration mismatch');
      selected.set(image.filename, bytes);
    }
  }
  if (selected.size !== definition.files.length) throw new Error('Workspace supplemental image is missing');
  return selected;
}

export async function readOnlyDelivery(environment = process.env) {
  if (environment.ABBY_ASSETS_S3_ENDPOINT !== 'https://sfo3.digitaloceanspaces.com'
    || environment.ABBY_ASSETS_S3_BUCKET !== 'abby-assets-releases'
    || environment.ABBY_ASSETS_S3_PREFIX !== 'releases' || !environment.ABBY_ASSETS_S3_REGION) throw new Error('Companion delivery needs the existing exact private reader settings');
  const { S3Client, GetObjectCommand } = await import('@aws-sdk/client-s3');
  const client = new S3Client({ endpoint: environment.ABBY_ASSETS_S3_ENDPOINT,
    region: environment.ABBY_ASSETS_S3_REGION, maxAttempts: 2 });
  return {
    async get(key, maximum) {
      if (!safe(key)) throw new Error('Unsafe delivery object key');
      try {
        const result = await client.send(new GetObjectCommand({ Bucket: environment.ABBY_ASSETS_S3_BUCKET, Key: `releases/${key}` }));
        if (result.ContentLength > maximum) { result.Body.destroy?.(); throw new Error('Delivery object exceeds its bound'); }
        return await bufferStream(result.Body, maximum);
      } catch { throw new Error('Pinned companion delivery read failed'); }
    },
    close() { client.destroy(); },
  };
}

export async function stageSupplementals({ destination, workspace = process.env.ABBY_COMPANION_WORKSPACE,
  definition = policy, reader, environment = process.env } = {}) {
  try { return { ...await verifySupplementals(destination, definition), unchanged: true }; } catch { /* Reverify all source bytes before replacement. */ }
  const guard = `${destination}.import-lock`;
  await mkdir(dirname(destination), { recursive: true });
  const lease = await open(guard, 'wx');
  const stage = join(dirname(destination), `.supplemental.stage-${randomUUID()}`);
  const previous = join(dirname(destination), `.supplemental.previous-${randomUUID()}`);
  let ownedReader;
  try {
    const original = await destinationState(destination, definition);
    let images;
    if (workspace) images = await localImages(workspace, definition);
    else {
      ownedReader = reader ? null : await readOnlyDelivery(environment);
      const source = reader || ownedReader;
      const indexBytes = await source.get(definition.index_key, 1024 ** 2);
      if (digest(indexBytes) !== definition.index_sha256) throw new Error('Delivery index digest mismatch');
      const index = JSON.parse(indexBytes);
      if (JSON.stringify(index.pin) !== JSON.stringify(definition.pin) || index.bucket !== 'abby-assets-releases'
        || index.endpoint !== 'https://sfo3.digitaloceanspaces.com' || index.prefix !== 'releases') throw new Error('Delivery index identity mismatch');
      const archive = index.objects?.verification_workspace;
      if (!archive || !safe(archive.key) || !archive.key.startsWith(`deliveries/${definition.pin.directory}/objects/`)
        || !Number.isSafeInteger(archive.bytes) || archive.bytes <= 0 || archive.bytes > 512 * 1024 ** 2) throw new Error('Invalid workspace locator');
      const zip = await source.get(archive.key, archive.bytes);
      if (zip.length !== archive.bytes || digest(zip) !== archive.sha256) throw new Error('Workspace ZIP digest mismatch');
      images = await verifyWorkspaceZip(zip, definition);
    }
    await mkdir(stage);
    for (const file of definition.files) {
      const bytes = images.get(file.filename);
      if (!safe(file.filename) || file.filename.includes('/') || !bytes || bytes.length !== file.bytes || digest(bytes) !== file.sha256) throw new Error('Supplemental payload mismatch');
      await writeFile(join(stage, file.filename), bytes);
    }
    await writeFile(join(stage, marker), JSON.stringify({ index_sha256: definition.index_sha256, inventory_sha256: definition.inventory_sha256 }));
    const result = await verifySupplementals(stage, definition);
    if (await destinationState(destination, definition) !== original) throw new Error('Supplemental destination changed during import; retained existing files');
    if (original !== null) {
      await rename(destination, previous);
      let unchanged = false;
      try { unchanged = await destinationState(previous, definition) === original; } catch { /* Restore all changed files below. */ }
      if (!unchanged) {
        await rename(previous, destination);
        throw new Error('Supplemental destination changed during replacement; retained existing files');
      }
    }
    try { await rename(stage, destination); }
    catch (error) { if (await exists(previous)) await rename(previous, destination); throw error; }
    if (await exists(previous)) {
      if (await destinationState(previous, definition) !== original) throw new Error('Supplemental previous files changed; retained recovery directory');
      await rm(previous, { recursive: true });
    }
    return { ...result, unchanged: false };
  } finally {
    ownedReader?.close();
    if (await exists(stage)) await rm(stage, { recursive: true });
    await lease.close(); await rm(guard);
  }
}

export const supplementalDestination = resolve(dirname(fileURLToPath(import.meta.url)), '../src/companion/supplemental');

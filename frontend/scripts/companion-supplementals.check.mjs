import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { crc32 } from 'node:zlib';
import { mkdtemp, mkdir, readFile, readlink, writeFile, symlink, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { stageSupplementals, verifySupplementals, verifyWorkspaceZip, readOnlyDelivery } from './companion-supplementals.mjs';
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const pin = { directory: 'synthetic/1/test', family_id: 'synthetic', manifest_sha256: 'a'.repeat(64), release_version: '1' };

async function setup(t) {
  const root = await mkdtemp(join(tmpdir(), 'abby-companion-supplement-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  const workspace = join(root, 'workspace'); await mkdir(join(workspace, 'assets'), { recursive: true });
  const bytes = Buffer.from('synthetic-image-bytes');
  const file = { path: 'assets/chick.png', filename: 'chick.png', sha256: hash(bytes), bytes: bytes.length };
  await writeFile(join(workspace, file.path), bytes);
  const inventory = Buffer.from(JSON.stringify({ pin, files: [{ path: file.path, sha256: file.sha256, bytes: file.bytes }] }));
  await writeFile(join(workspace, 'inventory.json'), inventory);
  return { root, workspace, bytes, inventory, definition: { pin, index_key: 'deliveries/synthetic/index.json', index_sha256: 'b'.repeat(64), inventory_sha256: hash(inventory), files: [file] }, destination: join(root, 'supplemental') };
}

// Stored ZIP fixtures exercise the real central-directory parser without any
// paid inputs, credentials, Python or additional writer dependency.
function zip(entries) {
  const files = [], records = []; let offset = 0;
  for (const { name, bytes, mode = 0o100600 } of entries) {
    const text = Buffer.from(name), crc = crc32(bytes);
    const local = Buffer.alloc(30); local.writeUInt32LE(0x04034b50); local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14); local.writeUInt32LE(bytes.length, 18); local.writeUInt32LE(bytes.length, 22); local.writeUInt16LE(text.length, 26);
    const central = Buffer.alloc(46); central.writeUInt32LE(0x02014b50); central.writeUInt16LE(0x314, 4); central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16); central.writeUInt32LE(bytes.length, 20); central.writeUInt32LE(bytes.length, 24); central.writeUInt16LE(text.length, 28);
    central.writeUInt32LE((mode * 65536) >>> 0, 38); central.writeUInt32LE(offset, 42);
    files.push(local, text, bytes); records.push(central, text); offset += local.length + text.length + bytes.length;
  }
  const end = Buffer.alloc(22); end.writeUInt32LE(0x06054b50); end.writeUInt16LE(entries.length, 8); end.writeUInt16LE(entries.length, 10);
  end.writeUInt32LE(records.reduce((sum, bytes) => sum + bytes.length, 0), 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...files, ...records, end]);
}

test('verified workspace stages only bound portraits and subsequent checks need no reader', async (t) => {
  const data = await setup(t);
  assert.deepEqual(await stageSupplementals(data), { files: 1, verified: true, unchanged: false });
  assert.deepEqual(await verifySupplementals(data.destination, data.definition), { files: 1, verified: true });
  assert.equal((await stageSupplementals({ ...data, workspace: undefined, reader: { get() { throw new Error('No network expected'); } } })).unchanged, true);
});

test('corrupt incoming images cannot replace the previous verified selection', async (t) => {
  const data = await setup(t); await stageSupplementals(data);
  await writeFile(join(data.workspace, 'assets/chick.png'), 'corrupt');
  await assert.rejects(stageSupplementals({ ...data, definition: { ...data.definition, index_sha256: 'c'.repeat(64) } }), /integrity mismatch/);
  assert.deepEqual(await readFile(join(data.destination, 'chick.png')), data.bytes);
  await verifySupplementals(data.destination, data.definition);
});

test('unmanaged files and source symlinks remain untouched', async (t) => {
  const data = await setup(t); await stageSupplementals(data);
  await writeFile(join(data.destination, 'owner-note.txt'), 'retain this file');
  await assert.rejects(stageSupplementals(data), /unknown supplemental files/);
  assert.equal(await readFile(join(data.destination, 'owner-note.txt'), 'utf8'), 'retain this file');
  await rm(join(data.workspace, 'assets/chick.png'));
  await symlink(join(data.destination, 'chick.png'), join(data.workspace, 'assets/chick.png'));
  await assert.rejects(stageSupplementals({ ...data, destination: join(data.root, 'other') }), /cannot contain links/);
});

test('an unmanaged dangling destination link is retained', async (t) => {
  const data = await setup(t), target = join(data.root, 'owner-missing-directory');
  await symlink(target, data.destination);
  await assert.rejects(stageSupplementals(data), /unmanaged supplemental directory/);
  assert.equal(await readlink(data.destination), target);
});

test('a delivery index is authenticated before any of its locators are used', async (t) => {
  const data = await setup(t); const reads = [];
  await assert.rejects(stageSupplementals({ ...data, workspace: undefined, reader: { async get(key) { reads.push(key); return Buffer.from('{}'); } } }), /index digest mismatch/);
  assert.deepEqual(reads, [data.definition.index_key]);
});

test('files added during a verified download are preserved and stop replacement', async (t) => {
  const data = await setup(t); await stageSupplementals(data);
  const archive = zip([{ name: 'inventory.json', bytes: data.inventory }, { name: 'assets/chick.png', bytes: data.bytes }]);
  const key = `deliveries/${pin.directory}/objects/workspace.zip`;
  const index = Buffer.from(JSON.stringify({ pin, bucket: 'abby-assets-releases', endpoint: 'https://sfo3.digitaloceanspaces.com', prefix: 'releases',
    objects: { verification_workspace: { key, bytes: archive.length, sha256: hash(archive) } } }));
  const definition = { ...data.definition, index_sha256: hash(index) };
  const reader = { async get(locator) {
    if (locator === definition.index_key) {
      await writeFile(join(data.destination, 'owner-note.txt'), 'retain during import');
      return index;
    }
    assert.equal(locator, key); return archive;
  } };
  await assert.rejects(stageSupplementals({ ...data, workspace: undefined, definition, reader }), /changed|unknown supplemental files/);
  assert.equal(await readFile(join(data.destination, 'owner-note.txt'), 'utf8'), 'retain during import');
  assert.deepEqual(await readFile(join(data.destination, 'chick.png')), data.bytes);
});

test('ZIP inventory and every file are verified without writing archive paths', async (t) => {
  const data = await setup(t);
  const entries = [{ name: 'inventory.json', bytes: data.inventory }, { name: 'assets/chick.png', bytes: data.bytes }];
  const images = await verifyWorkspaceZip(zip(entries), data.definition);
  assert.deepEqual(images.get('chick.png'), data.bytes);
  await assert.rejects(verifyWorkspaceZip(zip([...entries, { name: '../outside', bytes: Buffer.from('x') }]), data.definition), /invalid relative path|Unsafe/);
  await assert.rejects(verifyWorkspaceZip(zip([...entries, { name: 'link', bytes: Buffer.from('x'), mode: 0o120777 }]), data.definition), /Unsafe/);
  await assert.rejects(verifyWorkspaceZip(zip([...entries, { name: 'assets/chick.png', bytes: data.bytes }]), data.definition), /duplicate/);
  await assert.rejects(verifyWorkspaceZip(zip([entries[0], { ...entries[1], bytes: Buffer.from('changed') }]), data.definition), /inventory mismatch/);
});

test('the supplemental reader accepts only the existing scoped delivery store', async () => {
  await assert.rejects(readOnlyDelivery({ ABBY_ASSETS_S3_ENDPOINT: 'http://other.invalid' }), /exact private reader/);
});

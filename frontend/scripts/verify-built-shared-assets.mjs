import { createHash } from 'node:crypto';
import { access, readFile, readdir } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { verifyImport } from '@abby-assets/release-tools';
import { verifySupplementals, supplementalDestination } from './companion-supplementals.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export async function verifyBuiltPayloads(output, files) {
  const expected = new Map(files.map((file) => [file.sha256, file]));
  for (const file of await readdir(output)) {
    if (!/\.(glb|png|json)$/.test(file)) continue;
    const bytes = await readFile(join(output, file));
    const hash = createHash('sha256').update(bytes).digest('hex');
    if (expected.get(hash)?.bytes === bytes.length) expected.delete(hash);
  }
  if (expected.size) throw new Error(`Built shared asset payload is incomplete or changed: ${expected.size} pinned file(s) missing.`);
}

async function main() {
  const staged = join(root, 'src/avatar/shared');
  try { await access(staged); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  const lockPath = join(root, 'assets.lock.json');
  await verifyImport({ lock: lockPath, destination: staged });
  const lock = JSON.parse(await readFile(lockPath, 'utf8'));
  await verifySupplementals(supplementalDestination);
  const supplemental = JSON.parse(await readFile(join(root, '../shared/catalog/companion-supplemental.json'), 'utf8'));
  const expected = [...supplemental.files];
  for (const pin of lock.releases) {
    const manifest = JSON.parse(await readFile(join(staged, pin.directory, 'manifest.json'), 'utf8'));
    expected.push(...manifest.files);
  }
  const output = resolve(root, process.argv[2] || 'dist', 'assets');
  await verifyBuiltPayloads(output, expected);
  process.stdout.write('Finished bundle contains every pinned shared asset with matching bytes and SHA-256.\n');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await main();

import { access, readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { importReleases, verifyImport } from '@abby-assets/release-tools';
import { SHARED_ASSET_SECRET_NAMES, sharedAssetsEnvironment, sharedAssetsRequired } from './shared-assets-config.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const destination = resolve(root, 'src/avatar/shared');
const lock = resolve(root, 'assets.lock.json');
const mode = process.argv[2] || 'verify';

try {
  // BuildKit mounts remain server-side. Generic AWS secrets belong to the
  // existing media/meadow staging and are deliberately not read here.
  for (const name of SHARED_ASSET_SECRET_NAMES) {
    try {
      const value = await readFile(`/run/secrets/${name}`, 'utf8');
      if (value.length > 16_384) throw new Error(`Oversized build secret: ${name}`);
      process.env[name] = value.trim();
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  const scoped = sharedAssetsEnvironment(process.env);
  for (const name of ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'AWS_PROFILE', 'AWS_DEFAULT_PROFILE']) {
    if (scoped[name] === undefined) delete process.env[name];
    else process.env[name] = scoped[name];
  }
  if (!['verify', 'import', 'stage'].includes(mode)) throw new Error('Expected verify, import or stage');
  const required = sharedAssetsRequired(process.env.ABBY_SHARED_ASSETS_REQUIRED);
  let installed = true;
  try { await access(destination); } catch (error) { if (error.code !== 'ENOENT') throw error; installed = false; }
  const configured = Boolean(process.env.ABBY_ASSETS_RELEASE_ROOT || process.env.ABBY_ASSETS_S3_BUCKET);
  if (mode === 'import' || (mode === 'stage' && configured)) {
    const result = await importReleases({ lock, destination });
    process.stdout.write(`Shared assets verified: ${result.releases} pinned release(s), ${result.files} files.\n`);
  } else if (installed) {
    await verifyImport({ lock, destination });
    process.stdout.write('Shared assets match assets.lock.json.\n');
  } else if (required) {
    throw new Error('Shared assets are required. Run npm run assets:import with a private release source.');
  } else {
    process.stdout.write('Shared releases are absent; existing licensed art or labelled fallbacks are used.\n');
  }
} catch (error) {
  console.error(`Shared assets: ${error.message}`);
  process.exitCode = 1;
}

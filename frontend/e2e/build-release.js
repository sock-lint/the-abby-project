import { dirname, join, resolve } from 'node:path';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'vite';

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const [sourceDirectory, outDir, configFile, legacyOAuthNavigation] = process.argv.slice(2);
// Prevent the actual configuration from enabling its optional upload plugin.
delete process.env.SENTRY_AUTH_TOKEN;
let releaseConfig = configFile;
if (legacyOAuthNavigation === '--legacy-oauth-navigation') {
  // This opt-in release models the installed worker from before the OAuth
  // routing fix. All other releases build the canonical configuration intact.
  const source = await readFile(configFile, 'utf8');
  const legacySource = source.split('\n')
    .filter((line) => !line.trimStart().startsWith('/^\\/oauth'))
    .join('\n')
    .replace(/(from\s+)(['"])(\.[^'"]+)\2/g,
      (_, prefix, quote, specifier) => `${prefix}${quote}${resolve(dirname(configFile), specifier).replaceAll('\\', '/')}${quote}`);
  releaseConfig = join(sourceDirectory, 'vite.legacy.config.js');
  await writeFile(releaseConfig, legacySource);
}
await build({
  configFile: releaseConfig,
  root: sourceDirectory,
  envFile: false,
  envDir: sourceDirectory,
  publicDir: join(frontendRoot, 'public'),
  logLevel: 'warn',
  build: { outDir, emptyOutDir: true },
});

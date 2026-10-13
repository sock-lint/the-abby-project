import { createHash } from 'node:crypto';
import { execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, copyFile, writeFile, lstat, symlink, readFile } from 'node:fs/promises';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { chromium } from '@playwright/test';
import { LiveProcessGroup } from './live-process-group.mjs';
import { KIND, REPOSITORY, RECIPE_PATH, FILES, CHECKS, SCREENSHOTS, COMMIT, keys, requireValue, hash, recipe, bytes, noLinks, outsideGit, workbench, png, validateReceipt, contained, verifyAssetCopy } from './asset-checks-contract.mjs';

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const installation = resolve(frontend, '..');
const safeEnv = (home) => ({ PATH: '/usr/local/bin:/usr/bin:/bin', HOME: home, LANG: 'C.UTF-8', LC_ALL: 'C.UTF-8' });
const options = {};
for (let index = 2; index < process.argv.length; index += 1) {
  const key = process.argv[index];
  requireValue(['--capabilities', '--worktree', '--expected-commit', '--base-commit', '--issue', '--output', '--workbench-file', '--verify-receipt'].includes(key) && !Object.hasOwn(options, key), 'INVALID_ARGUMENTS');
  options[key] = key === '--capabilities' ? true : process.argv[++index];
}
let phase = 'CONFIGURATION';
let abort = false, browser, server, processGroup;
const timer = setTimeout(() => { abort = true; void browser?.close(); void server?.close(); void processGroup?.stop(); }, 600000);
timer.unref();
for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => {
  abort = true; void browser?.close(); void server?.close(); void processGroup?.stop();
});
const git = (directory, args) => execFileSync('/usr/bin/git', ['-C', directory, ...args],
  { env: safeEnv('/nonexistent'), encoding: 'utf8', maxBuffer: 128 * 1024 * 1024, timeout: 30000 }).trim();
async function sourceMarker() {
  const marker = JSON.parse(await bytes(join(frontend, '.abby-asset-source.json'), 4096));
  requireValue(keys(marker, ['schemaVersion', 'sourceCommit']) && marker.schemaVersion === 1 && COMMIT.test(marker.sourceCommit), 'INVALID_SOURCE_PIN');
  return marker.sourceCommit;
}
async function fingerprint() {
  const sourceCommit = await sourceMarker();
  const selected = await workbench(options['--workbench-file'] || '/etc/abby-asset-checks/workbench.json');
  const version = execFileSync(selected.config.blenderPath, ['--version'],
    { env: safeEnv('/nonexistent'), encoding: 'utf8', timeout: 15000, maxBuffer: 65536 }).split('\n')[0];
  requireValue(version === 'Blender ' + selected.config.blenderVersion, 'INVALID_BLENDER_VERSION');
  return { ...selected, sourceCommit };
}
function identity(sourceCommit) {
  const directory = options['--worktree'], head = options['--expected-commit'], base = options['--base-commit'], issue = Number(options['--issue']);
  requireValue(directory && resolve(directory) === directory && COMMIT.test(head) && COMMIT.test(base) && Number.isSafeInteger(issue) && issue > 0, 'INVALID_IDENTITY');
  requireValue(git(directory, ['rev-parse', 'HEAD']) === head && git(directory, ['status', '--porcelain', '--untracked-files=no']) === '', 'DIRTY_OR_CHANGED_HEAD');
  git(directory, ['merge-base', '--is-ancestor', base, head]);
  git(directory, ['merge-base', '--is-ancestor', sourceCommit, head]);
  const changed = git(directory, ['diff', '--name-only', '--no-renames', base, head]).split('\n').filter(Boolean);
  if (head !== sourceCommit) {
    requireValue(changed.every((path) => path === RECIPE_PATH || path.startsWith('frontend/src/companion/')
      || path.startsWith('frontend/src/components/companion/')), 'UNSUPPORTED_CHANGE');
  }
  const raw = execFileSync('/usr/bin/git', ['-C', directory, 'show', head + ':' + RECIPE_PATH], { env: safeEnv('/nonexistent'), maxBuffer: 16384, timeout: 30000 });
  return { directory, head, base, issue, selectedRecipe: recipe(JSON.parse(raw)), recipeSha256: hash(raw) };
}
async function runBlender(config, id, output) {
  const home = join(output, 'empty-home'); await mkdir(home, { mode: 0o700 });
  const child = spawn(config.blenderPath, ['--background', '--factory-startup', '--disable-autoexec', '--threads', '2', '--python-exit-code', '1',
    '--python', join(installation, 'scripts/r3f/woodland_texture_variant.py'), '--',
    '--baseline', join(config.baselineDirectory, 'woodland.glb'), '--output', join(output, 'variant'),
    '--verify-script', join(installation, 'scripts/r3f/verify_exports_blender.py'),
    '--max-dimension', String(id.selectedRecipe.maxDimension)], { env: safeEnv(home), stdio: 'ignore', detached: true });
  processGroup = new LiveProcessGroup(child); await processGroup.start();
  const [code] = await once(child, 'exit');
  const drained = await processGroup.stop(); processGroup = null;
  requireValue(code === 0 && drained && !abort, 'GENERATION_FAILED');
  const comparison = JSON.parse(await bytes(join(output, 'variant/comparison.json'), 8 * 1024 * 1024));
  requireValue(comparison.status === 'passed' && comparison.scope === 'private_evaluation'
    && comparison.geometryPreserved && comparison.originalJsonSemanticsPreserved
    && comparison.maxDimension === id.selectedRecipe.maxDimension, 'GENERATION_FAILED');
  const candidate = await bytes(join(output, 'variant', 'woodland-' + id.selectedRecipe.maxDimension + '.glb'));
  requireValue(hash(candidate) === comparison.candidate.sha256 && candidate.length === comparison.candidate.bytes, 'GENERATION_FAILED');
  return { sha256: hash(candidate), bytes: candidate.length };
}
async function snapshot(id, config, output, variant) {
  const revision = variant === 'baseline' ? id.base : id.head;
  const root = join(output, 'snapshot-' + variant); await mkdir(root, { mode: 0o700 });
  const entries = git(id.directory, ['ls-tree', '-r', revision, '--', 'frontend/src', 'frontend/public']).split('\n');
  requireValue(entries.every((line) => /^(100644|100755) blob /.test(line)), 'UNSUPPORTED_SOURCE_ENTRY');
  const archive = execFileSync('/usr/bin/git', ['-C', id.directory, 'archive', '--format=tar', revision, 'frontend/src', 'frontend/public'],
    { env: safeEnv('/nonexistent'), maxBuffer: 128 * 1024 * 1024, timeout: 30000 });
  execFileSync('/usr/bin/tar', ['-xf', '-', '-C', root], { input: archive, env: safeEnv('/nonexistent'), timeout: 30000 });
  const selected = join(root, 'frontend');
  // A candidate cannot enable executable Tailwind configuration/plugins.
  const cssFiles = git(id.directory, ['ls-tree', '-r', '--name-only', revision, '--', 'frontend/src']).split('\n').filter((name) => name.endsWith('.css'));
  for (const file of cssFiles) requireValue(!/@(?:plugin|config)\b/i.test(await readFile(join(root, file), 'utf8')), 'UNSUPPORTED_CSS_PLUGIN');
  await symlink(join(frontend, 'node_modules'), join(selected, 'node_modules'), 'dir');
  const fixture = join(selected, 'e2e/asset-checks'); await mkdir(fixture, { recursive: true, mode: 0o700 });
  for (const name of ['fixture.html', 'fixture.jsx', 'inspect.js']) await copyFile(join(frontend, 'e2e/asset-checks', name), join(fixture, name));
  const assets = join(selected, 'src/companion/licensed'); await mkdir(assets, { mode: 0o700 });
  for (const name of FILES) await copyFile(join(output, variant, name), join(assets, name));
  return selected;
}
async function verifySnapshot(id, selected, output, variant) {
  const revision = variant === 'baseline' ? id.base : id.head;
  if (variant === 'baseline') await verifyAssetCopy(join(output, 'baseline'), selected.config.files);
  const root = join(output, 'snapshot-' + variant);
  const listing = execFileSync('/usr/bin/git', ['-C', id.directory, 'ls-tree', '-rz', revision, '--', 'frontend/src', 'frontend/public'],
    { env: safeEnv('/nonexistent'), encoding: 'utf8', maxBuffer: 4 * 1024 * 1024, timeout: 30000 });
  for (const record of listing.split('\0').filter(Boolean)) {
    const match = record.match(/^(100644|100755) blob ([a-f0-9]{40})\t(.+)$/s);
    requireValue(match && !match[3].split('/').includes('..'), 'SNAPSHOT_CHANGED');
    const data = await bytes(join(root, match[3]));
    const blob = createHash('sha1').update('blob ' + data.length + '\0').update(data).digest('hex');
    requireValue(blob === match[2], 'SNAPSHOT_CHANGED');
  }
  for (const name of FILES) {
    const reference = await bytes(join(output, variant, name));
    requireValue(hash(await bytes(join(root, 'frontend/src/companion/licensed', name))) === hash(reference), 'SNAPSHOT_CHANGED');
  }
  for (const name of ['fixture.html', 'fixture.jsx', 'inspect.js']) {
    requireValue(hash(await bytes(join(root, 'frontend/e2e/asset-checks', name)))
      === hash(await bytes(join(frontend, 'e2e/asset-checks', name))), 'SNAPSHOT_CHANGED');
  }
  requireValue(selected.sourceInputsSha256, 'SNAPSHOT_CHANGED');
}
async function browserEvidence(id, baseline, candidate, output) {
  const result = [];
  let networkFailed = false;
  browser = await chromium.launch({ headless: true, env: safeEnv(join(output, 'empty-home')),
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--disable-background-networking'] });
  const version = browser.version();
  for (const [index, variant] of ['baseline', 'candidate'].entries()) {
    server = await createServer({ configFile: false, envDir: false, root: variant === 'baseline' ? baseline : candidate,
      plugins: [react({ babel: { babelrc: false, configFile: false } }), tailwindcss()], logLevel: 'silent',
      publicDir: false, cacheDir: join(output, 'vite-' + variant), server: { host: '127.0.0.1', port: 0, hmr: false,
        fs: { strict: true, allow: [variant === 'baseline' ? baseline : candidate, join(frontend, 'node_modules')] } },
      optimizeDeps: { include: ['react', 'react-dom/client', '@react-three/fiber', 'three', 'three/addons/loaders/GLTFLoader.js', 'three/addons/utils/SkeletonUtils.js'] } });
    await server.listen();
    const origin = 'http://127.0.0.1:' + server.httpServer.address().port;
    for (const [stage, width, height, layout] of [['chick', 375, 812, 'portrait'], ['bird', 375, 812, 'portrait'], ['chick', 812, 375, 'landscape']]) {
      requireValue(!abort, 'TIMED_OUT');
      const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block', reducedMotion: 'no-preference' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', () => errors.push('PAGE_ERROR'));
      await page.route('**/*', async (route) => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== origin || request.method() !== 'GET' || (url.pathname.startsWith('/api/') || url.pathname.startsWith('/__open-in-editor'))
          || request.headers().authorization || url.username || url.password) {
          networkFailed = true; return route.abort();
        }
        return route.continue();
      });
      await page.routeWebSocket('**/*', (socket) => {
        const url = new URL(socket.url());
        if (url.origin !== origin.replace('http:', 'ws:')) { networkFailed = true; socket.close(); }
        else socket.connectToServer();
      });
      await page.goto(origin + '/e2e/asset-checks/fixture.html?stage=' + stage, { waitUntil: 'networkidle', timeout: 45000 });
      await page.waitForFunction(() => ['passed', 'failed'].includes(document.querySelector('[data-testid="asset-inspection"]')?.textContent), { timeout: 45000 });
      requireValue(await page.getByTestId('asset-inspection').textContent() === 'passed', 'ASSET_INSPECTION_FAILED');
      await page.locator('.companion-preview-stage[aria-busy="false"]').waitFor({ timeout: 30000 });
      const checks = await page.evaluate(() => window.__ABBY_ASSET_CHECKS__);
      requireValue(['structure', 'materials', 'animation', 'grounding'].every((key) => checks?.[key] === true), 'ASSET_INSPECTION_FAILED');
      const canvas = page.locator('canvas');
      requireValue(await canvas.isVisible() && await page.getByRole('button', { name: 'Synthetic care controls' }).isEnabled(), 'RENDER_FAILED');
      await page.getByText('View', { exact: true }).click();
      await page.getByRole('checkbox', { name: 'Animate companion' }).uncheck();
      await page.getByText('View', { exact: true }).click();
      await page.waitForTimeout(150);
      requireValue(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'MOBILE_OVERFLOW');
      const name = variant + '-' + stage + '-' + layout;
      const path = join(output, 'screenshots', name + '.png');
      await page.locator('.companion-preview').screenshot({ path, animations: 'disabled' });
      const data = await bytes(path); const dimensions = png(data);
      result.push({ name, path, sha256: hash(data), ...dimensions });
      // Actual consumer error boundary must preserve its synthetic DOM control.
      await page.evaluate(() => {
        const gl = document.querySelector('canvas').getContext('webgl2');
        const extension = gl?.getExtension('WEBGL_lose_context');
        if (!extension) throw new Error('CONTEXT_LOSS_UNAVAILABLE');
        extension.loseContext();
      });
      await page.getByText('The 3D view could not load. Your companion and all controls are still available.').waitFor();
      requireValue(await page.getByRole('button', { name: 'Synthetic care controls' }).isEnabled(), 'FALLBACK_FAILED');
      requireValue(errors.length === 0 && !networkFailed, 'LOAD_OR_NETWORK_FAILURE');
      await context.close();
    }
    await server.close(); server = null;
    requireValue(index < 2, 'RENDER_FAILED');
  }
  await browser.close(); browser = null;
  return { screenshots: SCREENSHOTS.map((name) => result.find((row) => row.name === name)), chromium: version };
}
async function candidateFiles(output, selected) {
  const manifest = JSON.parse(await bytes(join(output, 'candidate/manifest.json'), 128 * 1024));
  requireValue(manifest.delivery_review === 'private_evaluation', 'INVALID_CANDIDATE');
  for (const name of FILES.filter((file) => file !== 'manifest.json')) {
    const data = await bytes(join(output, 'candidate', name));
    const expected = name === 'woodland.glb' ? manifest.models.woodland.sha256 : selected.config.files[name].sha256;
    requireValue(hash(data) === expected, 'CANDIDATE_CHANGED');
  }
  return hash(await bytes(join(output, 'candidate/manifest.json'), 128 * 1024));
}
async function verify(id, selected) {
  const path = options['--verify-receipt']; await outsideGit(path);
  const raw = await bytes(path, 128 * 1024), receipt = validateReceipt(JSON.parse(raw)), output = dirname(path);
  requireValue(receipt.headCommit === id.head && receipt.baseCommit === id.base && receipt.issue === id.issue
    && receipt.sourceCommit === selected.sourceCommit && receipt.catalogSha256 === selected.catalogSha256
    && receipt.recipeSha256 === id.recipeSha256 && receipt.sourceInputsSha256 === selected.sourceInputsSha256
    && receipt.sourceManifestSha256 === selected.sourceManifestSha256, 'RECEIPT_IDENTITY_CHANGED');
  requireValue(receipt.candidateManifestSha256 === await candidateFiles(output, selected), 'CANDIDATE_CHANGED');
  await verifySnapshot(id, selected, output, 'baseline');
  await verifySnapshot(id, selected, output, 'candidate');
  for (const item of receipt.screenshots) {
    requireValue(contained(join(output, 'screenshots'), item.path)
      && item.path === join(output, 'screenshots', item.name + '.png'), 'INVALID_SCREENSHOT_PATH');
    const data = await bytes(item.path); const dimensions = png(data);
    requireValue(hash(data) === item.sha256 && dimensions.width === item.width && dimensions.height === item.height, 'SCREENSHOT_CHANGED');
  }
  return { schemaVersion: 1, status: 'passed', receiptPath: path, evidenceSha256: hash(raw) };
}
async function main() {
  const selected = await fingerprint();
  if (options['--capabilities']) return { schemaVersion: 1, kind: KIND, ready: true, repository: REPOSITORY,
    sourceCommit: selected.sourceCommit, catalogSha256: selected.catalogSha256, assetKeys: ['woodland'],
    operations: ['woodland-texture-limit'], productionComponents: true, credentialsRequired: false };
  await noLinks(options['--worktree']);
  phase = 'IDENTITY';
  const id = identity(selected.sourceCommit);
  if (options['--verify-receipt']) { phase = 'RECEIPT_VERIFICATION'; return verify(id, selected); }
  const output = options['--output']; await outsideGit(output);
  requireValue(!contained(id.directory, output) && !contained(installation, output)
    && !contained(selected.config.baselineDirectory, output), 'OUTPUT_OVERLAP');
  try { await lstat(output); throw new Error('OUTPUT_EXISTS'); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await mkdir(output, { mode: 0o700 });
  await mkdir(join(output, 'screenshots'), { mode: 0o700 });
  phase = 'GENERATION';
  const generatedBinding = await runBlender(selected.config, id, output);
  for (const variant of ['baseline', 'candidate']) {
    await mkdir(join(output, variant), { mode: 0o700 });
    for (const name of FILES) await copyFile(join(selected.config.baselineDirectory, name), join(output, variant, name));
  }
  const generated = join(output, 'variant', 'woodland-' + id.selectedRecipe.maxDimension + '.glb');
  await copyFile(generated, join(output, 'candidate/woodland.glb'));
  const manifest = structuredClone(selected.manifest), data = await bytes(generated);
  requireValue(hash(data) === generatedBinding.sha256 && data.length === generatedBinding.bytes, 'CANDIDATE_CHANGED');
  manifest.models.woodland.sha256 = hash(data); manifest.models.woodland.bytes = data.length;
  const manifestBytes = JSON.stringify(manifest, null, 2) + '\n';
  await writeFile(join(output, 'candidate/manifest.json'), manifestBytes, { mode: 0o600 });
  const generatedManifestSha256 = hash(manifestBytes);
  phase = 'BASELINE_SNAPSHOT';
  const baseline = await snapshot(id, selected.config, output, 'baseline');
  phase = 'CANDIDATE_SNAPSHOT';
  const candidate = await snapshot(id, selected.config, output, 'candidate');
  await verifySnapshot(id, selected, output, 'baseline');
  await verifySnapshot(id, selected, output, 'candidate');
  phase = 'BROWSER';
  const rendered = await browserEvidence(id, baseline, candidate, output);
  await verifySnapshot(id, selected, output, 'baseline');
  await verifySnapshot(id, selected, output, 'candidate');
  requireValue(await candidateFiles(output, selected) === generatedManifestSha256, 'CANDIDATE_CHANGED');
  requireValue(hash(await bytes(join(output, 'candidate/woodland.glb'))) === generatedBinding.sha256, 'CANDIDATE_CHANGED');
  const checkedAt = new Date().toISOString();
  const report = validateReceipt({ schemaVersion: 1, kind: KIND, status: 'passed', scope: 'private_evaluation',
    headCommit: id.head, baseCommit: id.base, sourceCommit: selected.sourceCommit, issue: id.issue,
    checkedAt, expiresAt: new Date(Date.parse(checkedAt) + 3600000).toISOString(),
    catalogSha256: selected.catalogSha256, recipeSha256: id.recipeSha256,
    sourceManifestSha256: selected.sourceManifestSha256, sourceInputsSha256: selected.sourceInputsSha256,
    candidateManifestSha256: await candidateFiles(output, selected),
    toolVersions: { node: process.versions.node, blender: selected.config.blenderVersion, chromium: rendered.chromium },
    checks: Object.fromEntries(CHECKS.map((key) => [key, true])), screenshots: rendered.screenshots, failureCodes: [] });
  phase = 'FINAL_VERIFICATION';
  const current = await fingerprint(); requireValue(current.catalogSha256 === selected.catalogSha256, 'SOURCE_CHANGED');
  identity(selected.sourceCommit);
  const path = join(output, 'receipt.json'); const raw = JSON.stringify(report, null, 2) + '\n';
  await writeFile(path, raw, { mode: 0o600, flag: 'wx' });
  return { schemaVersion: 1, status: 'passed', receiptPath: path, evidenceSha256: hash(raw) };
}
try {
  process.umask(0o077);
  const result = await main();
  requireValue(!abort, 'TIMED_OUT');
  process.stdout.write(JSON.stringify(result) + '\n');
} catch (error) {
  const codes = new Set(['INVALID_CONTRACT','INVALID_ARGUMENTS','INVALID_PATH','SYMLINK_REFUSED','INVALID_FILE','FILE_CHANGED',
    'OUTPUT_INSIDE_GIT','INVALID_WORKBENCH','INVALID_BLENDER','INVALID_CATALOG','SOURCE_CHANGED','INVALID_MANIFEST',
    'INVALID_PNG','INVALID_RECEIPT','STALE_RECEIPT','FAILED_CHECKS','INVALID_SCREENSHOTS','INVALID_SOURCE_PIN',
    'INVALID_BLENDER_VERSION','INVALID_IDENTITY','DIRTY_OR_CHANGED_HEAD','UNSUPPORTED_CHANGE','INVALID_RECIPE',
    'GENERATION_FAILED','UNSUPPORTED_SOURCE_ENTRY','UNSUPPORTED_CSS_PLUGIN','TIMED_OUT','ASSET_INSPECTION_FAILED',
    'RENDER_FAILED','MOBILE_OVERFLOW','FALLBACK_FAILED','LOAD_OR_NETWORK_FAILURE','INVALID_CANDIDATE',
    'CANDIDATE_CHANGED','ASSET_COPY_CHANGED','SNAPSHOT_CHANGED','RECEIPT_IDENTITY_CHANGED','INVALID_SCREENSHOT_PATH','SCREENSHOT_CHANGED','OUTPUT_OVERLAP','OUTPUT_EXISTS']);
  const code = codes.has(error.message) ? error.message : 'ASSET_CHECK_FAILED';
  process.stderr.write(JSON.stringify({ schemaVersion: 1, status: 'failed', phase, code }) + '\n'); process.exitCode = 1;
} finally {
  clearTimeout(timer);
  await browser?.close().catch(() => {});
  await server?.close().catch(() => {});
  if (processGroup) await processGroup.stop();
}

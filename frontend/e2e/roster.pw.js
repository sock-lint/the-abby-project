import { chooseDropdown } from './dropdown-helpers.js';
import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

const roster = JSON.parse(readFileSync(new URL('../../shared/catalog/companion-roster.json', import.meta.url), 'utf8'));
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const manifestFor = (pin) => {
  const path = pin && new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url);
  return path && existsSync(path) ? JSON.parse(readFileSync(path, 'utf8')) : null;
};
const manifest = manifestFor(roster.release), bird = manifestFor(lock.releases.find(({ family_id }) => family_id === 'meshtint-bird-evolution'));
const fullMotions = process.env.ABBY_ROSTER_FULL_MOTIONS === '1';
let server, origin;
test.use({ reducedMotion: 'no-preference', launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });
test.beforeAll(async () => {
  // Coverage HTML and other concurrent verification output must not trigger a
  // dev-server full reload during a bound native playback observation.
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timeout = setTimeout(() => reject(new Error('Roster fixture startup timed out.')), 30_000);
    server.once('error', (error) => { clearTimeout(timeout); reject(error); });
    server.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Roster fixture exited ${code}.`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const address = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (address) { clearTimeout(timeout); resolve(address[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function play(page, status, id, expectedVariant, loop, expectedAction) {
  await chooseDropdown(page.getByRole('combobox', { name: 'Companion motion' }), id);
  await status.evaluate((element) => {
    window.__rosterPlaybackObserver?.disconnect();
    window.__rosterPlaybackHistory = [];
    const record = () => window.__rosterPlaybackHistory.push({ status: element.dataset.playbackStatus,
      variant: element.dataset.variantId, action: element.dataset.motionAction });
    window.__rosterPlaybackObserver = new MutationObserver(record);
    window.__rosterPlaybackObserver.observe(element, { attributes: true });
    record();
  });
  await page.getByRole('button', { name: 'Play motion', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(({ variant, action }) => ({
    observed: window.__rosterPlaybackHistory.some((state) => state.variant === variant && (!action || state.action === action)),
    hidden: document.hidden, reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
  }), { variant: expectedVariant, action: expectedAction })).toEqual({ observed: true, hidden: false, reduced: false });
  if (!loop) await expect(status).toHaveAttribute('data-playback-status', 'idle');
  await page.getByRole('button', { name: 'Return to rest', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect(status).toHaveAttribute('data-playback-status', 'idle');
}

for (const lineage of [...roster.families.map(({ lineage_id }) => lineage_id), 'chick']) {
  test(`${lineage}: four actual forms and native ${fullMotions ? 'complete' : 'sampled'} motion playback`, async ({ page }, info) => {
    // Full families contain up to 61 separate native creature takes plus 13
    // egg actions; leave their authored one-shot durations intact.
    test.setTimeout(fullMotions ? 600_000 : 180_000);
    test.skip(!manifest || (lineage === 'chick' && !bird), 'Private exact runtime payloads absent; real scene acceptance remains pending.');
    const errors = [], modelRequests = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('request', (request) => {
      const url = new URL(request.url());
      if (url.pathname.endsWith('.glb') && !url.searchParams.has('import')) modelRequests.push(url.pathname);
    });
    await page.route('**/*', (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${origin}/e2e/roster-fixture.html`);
    await chooseDropdown(page.getByRole('combobox', { name: 'Fixture family' }), lineage);
    const family = roster.families.find(({ lineage_id }) => lineage_id === lineage);
    let rendered = 0;
    for (const stage of ['baby', 'middle', 'grown']) {
      await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
      const status = page.getByRole('status', { name: 'Companion playback' });
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(status).toHaveAttribute('data-playback-status', 'idle', { timeout: 45_000 });
      const assetId = family?.stages[stage].asset_id || { baby: 'chick', middle: 'fledgling', grown: 'bird' }[stage];
      const asset = (lineage === 'chick' ? bird : manifest).assets.find(({ id }) => id === assetId);
      await expect(status).toHaveAttribute('data-variant-id', asset.default_variant);
      await page.screenshot({ path: info.outputPath(`${lineage}-${stage}.png`), fullPage: true });
      const before = modelRequests.length;
      await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
      await expect(status).toHaveAttribute('data-playback-status', 'idle');
      expect(modelRequests.length).toBe(before);
      await page.getByText('More motions', { exact: true }).click();
      const variants = fullMotions ? asset.variants : asset.variants.filter((variant) => variant.id === asset.default_variant || variant.animations?.clips.some((clip) => !clip.loop)).slice(0, 2);
      for (const variant of variants) {
        await play(page, status, variant.id, variant.id, variant.animations.clips[0].loop);
        rendered += 1;
      }
    }
    await page.getByRole('button', { name: 'Set egg', exact: true }).click();
    const beforeEgg = modelRequests.length;
    await expect(page.getByRole('button', { name: 'Egg', exact: true })).toHaveAttribute('aria-pressed', 'true');
    expect(modelRequests.length).toBe(beforeEgg);
    await page.getByRole('button', { name: 'Show 3D preview', exact: true }).click();
    if (lineage === 'chick') {
      await expect(page.getByRole('group', { name: 'Woodland display' })).toHaveAttribute('data-display-state', 'ready', { timeout: 45_000 });
    } else {
      const status = page.getByRole('status', { name: 'Family preview playback' });
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(status).toHaveAttribute('data-playback-status', 'idle', { timeout: 45_000 });
      await page.getByText('More motions', { exact: true }).click();
      const egg = manifest.assets.find(({ id }) => id === family.egg.asset_id).variants[0];
      for (const [action, clip] of Object.entries(egg.animations.actions)) {
        const metadata = egg.animations.clips.find(({ name }) => name === clip);
        await play(page, status, `native:${action}`, 'native', action === 'roll-forward-w-root' ? false : metadata.loop, action);
      }
    }
    await page.screenshot({ path: info.outputPath(`${lineage}-egg.png`), fullPage: true });
    await page.getByRole('button', { name: 'Unmount presentation', exact: true }).click();
    await expect(page.locator('canvas')).toHaveCount(0);
    expect(errors).toEqual([]);
    info.annotations.push({ type: 'native-creature-takes', description: String(rendered) });
  });
}

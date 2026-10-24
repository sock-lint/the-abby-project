import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { createHash } from 'node:crypto';
import { evaluationPin, evaluationPins, snakeCrabEvaluationPin } from './elemental-evaluation-server.mjs';
import { chooseDropdown as chooseSharedDropdown } from './dropdown-helpers.js';

// Real SwiftShader scene changes measured up to 12.5s before click completion.
// Keep actionability checks and the shared helper's default for other suites.
const chooseDropdown = (control, selection) => chooseSharedDropdown(control, selection, { timeout: 30_000 });

const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
function installedManifest(family) {
  const pin = lock.releases.find(({ family_id }) => family_id === family);
  const path = pin && new URL(`../src/avatar/shared/${pin.directory}/manifest.json`, import.meta.url);
  if (!path || !existsSync(path)) return null;
  const bytes = readFileSync(path);
  if (createHash('sha256').update(bytes).digest('hex') !== pin.manifest_sha256) throw new Error(`Installed manifest integrity failed: ${family}`);
  return JSON.parse(bytes.toString('utf8'));
}
const manifest = installedManifest('abby-elemental-companions');
const expansionManifest = installedManifest('abby-elemental-dragon-mushroom');
const rosterManifest = installedManifest('meshtint-companion-roster');
const roster = JSON.parse(readFileSync(new URL('../../shared/catalog/companion-roster.json', import.meta.url), 'utf8'));
const evaluationRoot = process.env.ABBY_ELEMENTAL_EVALUATION_ROOT;
const evaluationBytes = evaluationRoot ? readFileSync(`${evaluationRoot}/manifest.json`) : null;
const selectedEvaluationPin = evaluationBytes && evaluationPins.find(({ manifest_sha256 }) =>
  createHash('sha256').update(evaluationBytes).digest('hex') === manifest_sha256);
if (evaluationBytes && !selectedEvaluationPin) throw new Error('Private elemental evaluation manifest is not pinned.');
const evaluationManifest = evaluationBytes ? JSON.parse(evaluationBytes.toString('utf8')) : null;
for (const accepted of evaluationPins) {
  const canonical = lock.releases.find(({ family_id }) => family_id === accepted.family_id);
  if (canonical && Object.entries(accepted).some(([key, value]) => canonical[key] !== value)) {
    throw new Error(`Active elemental pin differs from the exact verified release: ${accepted.family_id}`);
  }
}
const beeBatManifest = evaluationManifest?.family_id === evaluationPin.family_id ? evaluationManifest : installedManifest(evaluationPin.family_id);
const snakeCrabManifest = evaluationManifest?.family_id === snakeCrabEvaluationPin.family_id ? evaluationManifest : installedManifest(snakeCrabEvaluationPin.family_id);
const beeBatSpecies = beeBatManifest ? ['meshtint-bee', 'meshtint-bat'] : [];
const snakeCrabSpecies = snakeCrabManifest ? ['meshtint-snake', 'meshtint-hermit-crab'] : [];
const reviewSpecies = [...beeBatSpecies, ...snakeCrabSpecies];
const evaluationSpecies = evaluationManifest ? [...new Set(evaluationManifest.appearance_bindings.stages.map(({ species_slug }) => species_slug))] : [];
const expansionSpecies = ['meshtint-dragon', 'meshtint-mushroom', ...reviewSpecies];
const allSpecies = ['chick', 'meshtint-wolf', ...expansionSpecies];
const elementalManifests = [manifest, expansionManifest, beeBatManifest, snakeCrabManifest].filter(Boolean);
const releaseBySpecies = new Map(elementalManifests.flatMap((release) => [...new Set(release.appearance_bindings.stages.map(({ species_slug }) => species_slug))]
  .map((species) => [species, release])));
const releaseFor = (species) => releaseBySpecies.get(species);
const uiImageIds = ['item-fire-potion', 'item-ice-potion', 'challenge-ember-nest', 'challenge-frost-nest', 'challenge-ember-trail', 'challenge-frost-trail',
  'challenge-ember-grove', 'challenge-frost-grove', 'challenge-ember-summit', 'challenge-frost-summit',
  ...(beeBatManifest ? ['review-bee-fire-acquisition-icon', 'review-bee-ice-acquisition-icon', 'review-bat-fire-acquisition-icon', 'review-bat-ice-acquisition-icon'] : []),
  ...(snakeCrabManifest ? ['review-snake-fire-acquisition-icon', 'review-snake-ice-acquisition-icon', 'review-hermit-crab-fire-acquisition-icon', 'review-hermit-crab-ice-acquisition-icon'] : [])];
const stages = ['baby', 'middle', 'grown'];
const fullMotions = process.env.ABBY_ELEMENTAL_FULL_MOTIONS === '1';
let server, origin;
test.use({ viewport: { width: 390, height: 844 }, reducedMotion: 'no-preference',
  launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });
test.beforeAll(async () => {
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; import { elementalEvaluationPlugin } from './e2e/elemental-evaluation-server.mjs'; const server = await createServer({ plugins: [await elementalEvaluationPlugin()], server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: { ...Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))), ...(evaluationRoot ? { ABBY_ELEMENTAL_EVALUATION_ROOT: evaluationRoot } : {}) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timeout = setTimeout(() => reject(new Error('Elemental fixture startup timed out.')), 30_000);
    server.once('error', (error) => { clearTimeout(timeout); reject(error); });
    server.once('exit', (code) => { clearTimeout(timeout); reject(new Error(`Elemental fixture exited ${code}.`)); });
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

async function open(page, species = 'chick', potion = 'fire') {
  const errors = [], mutations = [], requests = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    requests.push(request.url());
    if (!['GET', 'HEAD'].includes(request.method())) mutations.push(request.method());
  });
  // This fixture must never contact an application or publication service.
  await page.route('**/*', (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.goto(`${origin}/e2e/elemental-fixture.html`);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture species' }), species);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture potion' }), potion);
  await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-elemental-installed', 'true');
  const explicit = evaluationSpecies.includes(species);
  await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-delivery-mode', explicit ? 'evaluation' : 'canonical');
  await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-explicit-staged-prop', String(explicit));
  return { errors, mutations, requests };
}
const playback = (page) => page.getByRole('status', { name: 'Companion playback', exact: true });
function stageBinding(release, species, potion, stage) {
  return release.appearance_bindings.stages.find((binding) => binding.species_slug === species && binding.potion_slug === potion
    && binding.lifecycle_stage === stage && binding.motion === 'idle');
}
function nativeVariant(release, binding) {
  return release.assets.find(({ id }) => id === binding.asset_id).variants.find(({ id }) => id === binding.variant_id);
}
async function resting(page, stage, name = 'Companion playback', scope = page, variantId) {
  const status = scope.getByRole('status', { name, exact: true });
  await scope.locator('canvas').scrollIntoViewIfNeeded();
  await expect(status).toHaveAttribute('data-playback-status', 'idle', { timeout: 45_000 });
  await expect(status).toHaveAttribute('data-stage', stage);
  if (!variantId) {
    const diagnostics = page.getByLabel('Fixture diagnostics');
    const species = await diagnostics.getAttribute('data-selected-species'), potion = await diagnostics.getAttribute('data-selected-potion');
    variantId = stageBinding(releaseFor(species), species, potion, stage).variant_id;
  }
  await expect(status).toHaveAttribute('data-variant-id', variantId);
}
async function observePlayback(page) {
  await page.locator('main').evaluate((element) => {
    window.__elementalObserver?.disconnect(); window.__elementalHistory = [];
    const record = () => {
      const status = element.querySelector('[aria-label="Companion playback"]');
      if (status) window.__elementalHistory.push({ status: status.dataset.playbackStatus, variant: status.dataset.variantId, stage: status.dataset.stage });
    };
    window.__elementalObserver = new MutationObserver(record);
    window.__elementalObserver.observe(element, { attributes: true, childList: true, subtree: true }); record();
  });
}
async function play(page, binding, release) {
  const variant = nativeVariant(release, binding);
  const clip = variant.animations.clips.find(({ name }) => name === variant.animations.actions[binding.action]);
  await chooseDropdown(page.getByRole('combobox', { name: 'Companion motion' }), binding.motion);
  await observePlayback(page);
  await page.getByRole('button', { name: 'Play motion', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect.poll(() => page.evaluate(({ id, idle }) => window.__elementalHistory.some(({ variant, status }) => variant === id
    && status === (idle ? 'idle' : 'playing')), { id: binding.variant_id, idle: binding.motion === 'idle' })).toBe(true);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  if (!clip.loop) await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
  await page.getByRole('button', { name: 'Return to rest', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  await expect(playback(page)).toHaveAttribute('data-playback-status', 'idle');
}

for (const species of allSpecies) {
  for (const potion of ['fire', 'ice']) {
    test(`${species}/${potion}: actual owned and Hatchery forms, exact portraits and ${fullMotions ? 'all' : 'sampled'} native takes`, async ({ page }, info) => {
      test.setTimeout(fullMotions ? 600_000 : 240_000);
      const release = releaseFor(species);
      test.skip(!release, 'Exact private elemental payloads are not installed; this artwork check was not executed.');
      const { errors, mutations, requests } = await open(page, species, potion);
      if (reviewSpecies.includes(species)) await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-populated-woodland', 'true');
      let rendered = 0;
      for (const stage of stages) {
        if (expansionSpecies.includes(species)) await observePlayback(page);
        await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
        await resting(page, stage);
        if (expansionSpecies.includes(species)) expect(await page.evaluate(() => window.__elementalHistory.some(({ status }) => status === 'evolving'))).toBe(false);
        await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-appearance-id', `${species}-${potion}-${stage}`);
        await page.screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-live.png`), fullPage: true });
        if (reviewSpecies.includes(species)) await page.locator('.companion-preview').screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-owner-preview.png`) });
        await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
        await resting(page, stage);
        await page.getByText('More motions', { exact: true }).click();
        const bindings = release.appearance_bindings.stages.filter((binding) => binding.species_slug === species && binding.potion_slug === potion && binding.lifecycle_stage === stage);
        const control = page.getByRole('combobox', { name: 'Companion motion' });
        await control.click({ timeout: 6_000 });
        const listbox = page.locator(`[id=${JSON.stringify(await control.getAttribute('aria-controls'))}]`);
        const values = await listbox.getByRole('option').evaluateAll((options) => options.map((option) => option.dataset.value));
        expect(values).toEqual(bindings.map(({ motion }) => motion));
        expect(new Set(values).size).toBe(values.length);
        await control.press('Escape', { timeout: 6_000 });
        const motions = fullMotions ? bindings : bindings.filter(({ motion }) => ['idle', 'fly-idle', 'turn-left'].includes(motion));
        for (const binding of motions) { await play(page, binding, release); rendered += 1; }
      }
      await page.reload(); await resting(page, 'grown');
      await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-selected-species', species);
      await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-selected-potion', potion);
      await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-egg-item-slug', species === 'chick' ? 'chick-egg' : `${species}-egg`);
      await chooseDropdown(page.getByRole('combobox', { name: 'Fixture surface' }), 'hatchery');
      const family = page.getByRole('region', { name: 'Family artwork preview' });
      await expect(family.getByRole('button', { name: 'Egg', exact: true })).toHaveAttribute('aria-pressed', 'true');
      const eggUrl = await family.getByRole('img').getAttribute('src');
      await chooseDropdown(page.getByRole('combobox', { name: 'Fixture potion' }), potion === 'fire' ? 'ice' : 'fire');
      await expect(family.getByRole('img')).toHaveAttribute('src', eggUrl);
      await chooseDropdown(page.getByRole('combobox', { name: 'Fixture potion' }), potion);
      for (const stage of stages) {
        await family.getByRole('button', { name: `${stage[0].toUpperCase()}${stage.slice(1)}`, exact: true }).click();
        const image = family.getByRole('img');
        await expect(image).toHaveAttribute('src', /\.png/);
        await expect.poll(() => image.evaluate((element) => element.complete && element.naturalWidth === 256)).toBe(true);
        await page.getByRole('button', { name: 'Show 3D preview', exact: true }).click();
        await resting(page, stage, 'Family preview playback');
        await page.screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-hatchery.png`), fullPage: true });
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.getByRole('button', { name: 'Unmount presentation', exact: true }).click();
      await expect(page.locator('canvas')).toHaveCount(0);
      expect(errors).toEqual([]); expect(mutations).toEqual([]);
      if (reviewSpecies.includes(species)) {
        const delivered = requests.filter((url) => release.files.some(({ path }) => new URL(url).pathname.endsWith(`/${path}`)));
        expect(delivered.length).toBeGreaterThan(0);
        const explicit = evaluationSpecies.includes(species), delivery = explicit ? 'evaluation' : 'canonical';
        const pin = explicit ? selectedEvaluationPin : lock.releases.find(({ family_id }) => family_id === release.family_id);
        const prefix = explicit ? '/__abby_elemental_evaluation__/' : `/avatar/shared/${pin.directory}/`;
        expect(delivered.every((url) => new URL(url).pathname.includes(prefix))).toBe(true);
        info.annotations.push({ type: 'release-delivery', description: `${delivery}; explicit staged prop ${explicit}; ${release.family_id}` });
      }
      info.annotations.push({ type: 'native-takes-rendered', description: String(rendered) });
      info.annotations.push({ type: 'woodland', description: 'See fixture diagnostics: private populated Woodland is independently required.' });
    });
  }
}

test('all installed exact portraits and catalog images use exact 256px art in a narrow layout', async ({ page }, info) => {
  test.skip(!manifest || !expansionManifest, 'Exact private elemental payloads are not installed; this image check was not executed.');
  const { errors, mutations } = await open(page);
  await chooseDropdown(page.getByRole('combobox', { name: 'Fixture surface' }), 'portraits');
  const gallery = page.getByRole('region', { name: 'Elemental portrait and catalog images' });
  await expect(gallery.locator('img')).toHaveCount(allSpecies.length * 6 + uiImageIds.length);
  // Inspect every row so browser-native lazy images load before decoding.
  for (const image of await gallery.locator('img').all()) await image.scrollIntoViewIfNeeded();
  await expect.poll(() => gallery.locator('img').evaluateAll((images) => images.every((image) => image.complete && image.naturalWidth === 256))).toBe(true);
  for (const binding of elementalManifests.flatMap((release) => release.appearance_bindings.stages).filter(({ motion }) => motion === 'idle')) {
    const portrait = releaseFor(binding.species_slug).assets.find(({ id }) => id === binding.portrait_asset_id).variants.find(({ id }) => id === binding.portrait_variant_id);
    await expect(gallery.getByTestId(`${binding.species_slug}-${binding.potion_slug}-${binding.lifecycle_stage}`).locator('img')).toHaveAttribute('src', new RegExp(portrait.file));
  }
  for (const id of uiImageIds) {
    const asset = elementalManifests.flatMap((release) => release.assets).find((entry) => entry.id === id);
    const image = asset.variants.find(({ id: variantId }) => variantId === 'icon');
    await expect(gallery.getByTestId(id).locator('img')).toHaveAttribute('src', new RegExp(image.file));
  }
  expect(await gallery.locator('img').evaluateAll((images) => images.every((image) => !image.style.filter.includes('hue-rotate')))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath('all-elemental-portraits-and-ui.png'), fullPage: true });
  expect(errors).toEqual([]); expect(mutations).toEqual([]);
});

for (const potion of ['fire', 'ice']) {
  test(`Chick/${potion}: both confirmed step transitions, direct jump and saved-state reload`, async ({ page }, info) => {
    test.skip(!manifest, 'Exact private elemental payloads are not installed; this evolution check was not executed.');
    const { errors, mutations } = await open(page, 'chick', potion);
    await resting(page, 'baby');
    const seen = [];
    page.on('request', (request) => { if (request.url().endsWith('.glb')) seen.push(request.url()); });
    for (const stage of ['middle', 'grown']) {
      await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
      await page.locator('canvas').scrollIntoViewIfNeeded();
      await expect(playback(page)).toHaveAttribute('data-playback-status', 'evolving');
      await page.screenshot({ path: info.outputPath(`chick-${potion}-evolving-${stage}.png`), fullPage: true });
      await resting(page, stage);
    }
    const beforeReload = seen.length;
    await page.getByRole('button', { name: 'Reload saved companion', exact: true }).click();
    await resting(page, 'grown'); expect(seen.length).toBe(beforeReload);
    await page.reload(); await resting(page, 'grown');
    await page.getByRole('button', { name: 'Set baby', exact: true }).click(); await resting(page, 'baby');
    const beforeJump = seen.length;
    await page.getByRole('button', { name: 'Set grown', exact: true }).click();
    await page.locator('canvas').scrollIntoViewIfNeeded();
    await expect(playback(page)).toHaveAttribute('data-playback-status', 'evolving');
    await resting(page, 'grown');
    const transitionFiles = manifest.appearance_bindings.transitions.filter((binding) => binding.species_slug === 'chick' && binding.potion_slug === potion)
      .map((binding) => manifest.assets.find(({ id }) => id === binding.asset_id).variants.find(({ id }) => id === binding.variant_id).file);
    for (const file of transitionFiles) expect(seen.slice(beforeJump).some((url) => url.endsWith(file)), `Direct jump must load the exact ${potion} ${file} transition.`).toBe(true);
    await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
    expect(errors).toEqual([]); expect(mutations).toEqual([]);
  });
}

test('reduced motion goes directly to the confirmed target; an unsupported identity keeps readable controls', async ({ page }, info) => {
  test.skip(!manifest, 'Exact private elemental payloads are not installed; this reduced-motion check was not executed.');
  const { errors, mutations } = await open(page);
  await resting(page, 'baby');
  const transitions = manifest.appearance_bindings.transitions.map((binding) => manifest.assets.find(({ id }) => id === binding.asset_id)
    .variants.find(({ id }) => id === binding.variant_id).file);
  const requests = [];
  page.on('request', (request) => { if (transitions.some((file) => request.url().endsWith(file))) requests.push(request.url()); });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('button', { name: 'Set grown', exact: true }).click(); await resting(page, 'grown');
  expect(requests).toEqual([]);
  await expect(page.getByRole('button', { name: 'Fly together', exact: true })).toBeDisabled();
  await page.screenshot({ path: info.outputPath('reduced-motion-confirmed-bird.png'), fullPage: true });
  await page.getByRole('button', { name: 'Use unsupported identity', exact: true }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.getByRole('img', { name: /Saved companion, your companion/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
  expect(errors).toEqual([]); expect(mutations).toEqual([]);
});

for (const [species, potion] of [['meshtint-wolf', 'ice'], ...expansionSpecies.flatMap((species) => ['fire', 'ice'].map((potion) => [species, potion]))]) {
  test(`${species}/${potion}: failed exact model retains its portrait and controls; retry restores the same appearance`, async ({ page }, info) => {
    const release = releaseFor(species);
    test.skip(!release, 'Exact private elemental payloads are not installed; this recovery check was not executed.');
    const { errors, mutations } = await open(page, species, potion);
    await resting(page, 'baby');
    const variant = nativeVariant(release, stageBinding(release, species, potion, 'middle'));
    const pattern = `**/${variant.file}`;
    await page.route(pattern, (route) => route.abort('failed'));
    await page.getByRole('button', { name: 'Set middle', exact: true }).click();
    await expect(page.getByText('The 3D view could not load. Your companion and all controls are still available.')).toBeVisible();
    await expect(page.getByRole('img', { name: /, your companion$/ })).toHaveAttribute('src', /\.png/);
    await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
    await page.screenshot({ path: info.outputPath(`failed-exact-${species}-${potion}-model.png`), fullPage: true });
    await page.unroute(pattern);
    await page.getByText('View', { exact: true }).click();
    await page.getByRole('button', { name: 'Retry 3D woodland', exact: true }).click();
    await resting(page, 'middle');
    expect(errors.filter((message) => !/fetch|load|GLB|Failed/i.test(message))).toEqual([]);
    expect(mutations).toEqual([]);
  });
}

for (const species of expansionSpecies) {
  test(`${species}: both elements preserve destination idle, saved identity and readable controls with reduced motion`, async ({ page }, info) => {
    test.setTimeout(180_000);
    test.skip(!releaseFor(species), 'Exact private elemental payloads are not installed; this reduced-motion check was not executed.');
    const { errors, mutations } = await open(page, species, 'fire');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    for (const potion of ['fire', 'ice']) {
      await chooseDropdown(page.getByRole('combobox', { name: 'Fixture potion' }), potion);
      for (const stage of stages) {
        await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
        await resting(page, stage);
        await expect(page.getByRole('button', { name: 'Look around', exact: true })).toBeDisabled();
        await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
        await page.screenshot({ path: info.outputPath(`${species}-${potion}-${stage}-reduced-motion.png`), fullPage: true });
      }
      await page.reload(); await resting(page, 'grown');
      await expect(page.getByLabel('Fixture diagnostics')).toHaveAttribute('data-selected-potion', potion);
      await page.getByRole('button', { name: 'Use unsupported identity', exact: true }).click();
      await expect(page.locator('canvas')).toHaveCount(0);
      await expect(page.getByRole('img', { name: /Saved companion, your companion/ })).toBeVisible();
      await expect(page.getByRole('button', { name: 'Existing care control', exact: true })).toBeEnabled();
    }
    expect(errors).toEqual([]); expect(mutations).toEqual([]);
  });

  test(`${species}: Base, Fire and Ice render together at every stage with independent reduced-motion presentation`, async ({ page }, info) => {
    test.setTimeout(240_000);
    test.skip(!releaseFor(species) || !rosterManifest, 'Exact private elemental and Base payloads are not installed; this coexistence check was not executed.');
    const { errors, mutations } = await open(page, species, 'fire');
    await chooseDropdown(page.getByRole('combobox', { name: 'Fixture surface' }), 'coexistence');
    const coexistence = page.getByRole('region', { name: 'Base, Fire and Ice coexistence' });
    const baseFamily = roster.families.find(({ species_slug }) => species_slug === species);
    for (const stage of stages) {
      await page.getByRole('button', { name: `Set ${stage}`, exact: true }).click();
      for (const reduced of ['no-preference', 'reduce']) {
        await page.emulateMedia({ reducedMotion: reduced });
        await expect(coexistence.locator('canvas')).toHaveCount(3);
        for (const potion of ['base', 'fire', 'ice']) {
          const card = coexistence.getByTestId(`coexist-${potion}`);
          const variantId = potion === 'base' ? baseFamily.stages[stage].default_variant_id
            : stageBinding(releaseFor(species), species, potion, stage).variant_id;
          await resting(page, stage, 'Companion playback', card, variantId);
          const playButton = card.getByRole('button', { name: 'Look around', exact: true });
          if (reduced === 'reduce') await expect(playButton).toBeDisabled();
          else await expect(playButton).toBeEnabled();
        }
        await page.screenshot({ path: info.outputPath(`${species}-${stage}-base-fire-ice-${reduced}.png`), fullPage: true });
      }
    }
    await page.getByRole('button', { name: 'Unmount presentation', exact: true }).click();
    await expect(page.locator('canvas')).toHaveCount(0);
    expect(errors).toEqual([]); expect(mutations).toEqual([]);
  });
}

test('exact Base, Fire and Ice loader instances isolate materials, textures, mutation and disposal at all installed family stages', async ({ page }, info) => {
  test.setTimeout(180_000);
  test.skip(!expansionManifest || !rosterManifest, 'Exact private elemental and Base payloads are not installed; this material-isolation check was not executed.');
  const { errors, mutations } = await open(page, 'meshtint-dragon', 'fire');
  const result = await page.evaluate(async () => {
    const modulePath = '/__abby_elemental_evaluation__/module.js';
    const evaluation = (await import(/* @vite-ignore */ modulePath)).default;
    return (await import('/e2e/elemental-inspection.js')).inspectElementalMaterialIsolation(evaluation);
  });
  expect(result.instances).toBe(expansionSpecies.length * stages.length * 4);
  expect(result.independent).toBe(true);
  expect(result.groups).toHaveLength(expansionSpecies.length * stages.length);
  expect(result.groups.map(({ species, stage }) => `${species}/${stage}`).sort()).toEqual(
    expansionSpecies.flatMap((species) => stages.map((stage) => `${species}/${stage}`)).sort());
  for (const group of result.groups) {
    expect(group.instances).toBe(4);
    expect(group.independent).toBe(true);
    expect(group.mutation_isolated).toBe(true);
    expect(group.disposal_isolated).toBe(true);
    expect(group.resources).toHaveLength(4);
    for (const resources of group.resources) {
      expect(resources.materials).toBeGreaterThan(0);
      expect(resources.textures).toBeGreaterThan(0);
      expect(resources.geometries).toBeGreaterThan(0);
    }
  }
  await info.attach('material-isolation-proof', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
  expect(errors).toEqual([]); expect(mutations).toEqual([]);
});


test('private evaluation delivery is pinned, read-only and limited to its verified inventory', async ({ request }) => {
  const response = await request.get(`${origin}/__abby_elemental_evaluation__/module.js`);
  expect(response.ok()).toBe(true);
  const source = await response.text();
  if (evaluationManifest) {
    expect(source).toContain(selectedEvaluationPin.manifest_sha256);
    expect(source).not.toContain(evaluationRoot);
  } else expect(source).toBe('export default null;');
  expect((await request.post(`${origin}/__abby_elemental_evaluation__/module.js`)).status()).toBe(405);
  expect((await request.get(`${origin}/__abby_elemental_evaluation__/objects/unknown.glb`)).status()).toBe(404);
  expect((await request.get(`${origin}/__abby_elemental_evaluation__/..%2fpackage.json`)).status()).toBe(404);
});

import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, readFile } from 'node:fs/promises';
import { existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

const roster = JSON.parse(await readFile(new URL('../../shared/catalog/companion-roster.json', import.meta.url), 'utf8'));
const potion = (slug, id) => ({ id, slug, name: slug[0].toUpperCase() + slug.slice(1), rarity: slug === 'base' ? 'common' : 'rare', catalog_available: true });
const potions = [potion('base', 1), potion('fire', 2), potion('ice', 3)];
const elemental = new Set(['chick', 'meshtint-wolf', 'meshtint-dragon', 'meshtint-mushroom']);
const familyRows = [{ species_slug: 'chick', sprite_key: 'cute-chick', name: 'Chick' }, ...roster.families];
const savedPath = '/quests?tab=trials&goal=goal%3A83';
const lock = JSON.parse(readFileSync(new URL('../assets.lock.json', import.meta.url), 'utf8'));
const expansion = lock.releases.find((release) => release.family_id === 'abby-elemental-dragon-mushroom');
const expansionRoot = expansion && new URL(`../src/avatar/shared/${expansion.directory}/`, import.meta.url);
const expansionManifest = expansionRoot && existsSync(new URL('manifest.json', expansionRoot))
  ? JSON.parse(readFileSync(new URL('manifest.json', expansionRoot), 'utf8')) : null;
const installedExpansion = expansionManifest?.files.every((file) => existsSync(new URL(file.path, expansionRoot)));
let server, origin;
test.use({ launchOptions: { args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] } });

function scenarioData(mode = 'empty') {
  const species = familyRows.map((family, index) => ({ id: index + 100, slug: family.species_slug, sprite_key: family.sprite_key,
    name: family.name, icon: '🐾', catalog_available: true, discovered: false, owned_pet_ids: [], owned_mount_potion_ids: [],
    available_potions: potions.filter((entry) => entry.slug === 'base' || elemental.has(family.species_slug)).map((entry) => ({ ...entry, acquisition_challenges: [] })) }));
  const mushroom = species.find((entry) => entry.slug === 'meshtint-mushroom');
  mushroom.available_potions.find((entry) => entry.slug === 'fire').acquisition_challenges = [{
    definition_id: 77, name: 'Ember Grove', offer_available: false, target: '10', duration_days: 180,
    attempt: { id: 'goal:83', name: 'Saved Ember Grove', status: 'active', progress: '7', target: '12', ends_at: null, retry_available: false }, path: savedPath,
  }];
  const stable = { pets: [], mounts: [] };
  let incubation = null;
  const incubatingFamily = mode === 'ready' ? species[0] : mushroom;
  const egg = { id: 501, slug: incubatingFamily.slug === 'chick' ? 'chick-egg' : `${incubatingFamily.slug}-egg`,
    name: `${incubatingFamily.name} Egg`, item_type: 'egg', pet_species_slug: incubatingFamily.slug,
    pet_species_name: incubatingFamily.name, metadata: { species: incubatingFamily.slug } };
  if (mode === 'mixed') {
    mushroom.discovered = true; mushroom.owned_pet_ids = [72]; mushroom.owned_mount_potion_ids = [1];
    stable.pets = [{ id: 72, species: mushroom, potion: potions[1], lifecycle_stage: 'baby', growth_points: 49, evolved_to_mount: false }];
    stable.mounts = [{ id: 71, species: mushroom, potion: potions[0], lifecycle_stage: 'grown' }];
  }
  if (['mixed', 'ready'].includes(mode)) {
    const selected = mode === 'ready' ? potions[1] : potions[2];
    incubation = { id: 73, species: incubatingFamily, potion_type: selected, egg,
      potion: { id: 600 + selected.id, name: `${selected.name} Potion`, item_type: 'potion', metadata: { variant: selected.slug } },
      status: mode === 'ready' ? 'ready' : 'incubating', is_ready: mode === 'ready', remaining_seconds: mode === 'ready' ? 0 : 3600 };
  }
  const inventory = mode === 'supplies' ? [{ quantity: 1, item: { ...egg, catalog_available: true } },
    ...potions.slice(0, 2).map((entry) => ({ quantity: 1, item: { id: 600 + entry.id, slug: `${entry.slug}-potion`,
      name: `${entry.name} Potion`, item_type: 'potion', catalog_available: true, metadata: { variant: entry.slug } } }))] : [];
  return { catalog: { species, potions, totals: { species: species.length, discovered_species: mode === 'mixed' ? 1 : 0, mounts_possible: 23, mounts_owned: mode === 'mixed' ? 1 : 0 } },
    stable, inventory, incubations: { incubation, duration_seconds: 86400, server_now: '2026-10-22T12:00:00Z' } };
}

test.beforeAll(async () => {
  server = spawn(process.execPath, ['--input-type=module', '-e', "import { createServer } from 'vite'; const server = await createServer({ server: { host: '127.0.0.1', port: 0, hmr: false, watch: null } }); await server.listen(); server.printUrls();"], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), stdio: ['ignore', 'pipe', 'pipe'],
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error('Local Hatchery fixture startup timed out.')), 30000);
    server.once('error', (error) => { clearTimeout(timer); reject(error); });
    server.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Local fixture exited ${code}.`)); });
    server.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString()); const match = output.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
  });
});
test.afterAll(async () => {
  if (server?.exitCode === null) { const stopped = once(server, 'exit'); server.kill(); await stopped; }
});

async function open(page, { mode = 'empty', query = '', catalogUnavailable = () => false } = {}) {
  const data = scenarioData(mode), errors = [], mutations = [], external = [], unexpectedApi = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    if (!['GET', 'HEAD'].includes(request.method())) { mutations.push(request.method()); return route.abort(); }
    const payload = { '/api/pets/codex/': data.catalog, '/api/pets/stable/': data.stable,
      '/api/inventory/': data.inventory, '/api/pets/incubations/': data.incubations }[url.pathname];
    if (url.pathname === '/api/pets/codex/' && catalogUnavailable()) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Companion catalog temporarily unavailable' }) });
    if (payload !== undefined) return route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
    if (url.pathname.startsWith('/api/')) { unexpectedApi.push(url.pathname); return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }); }
    return route.continue();
  });
  await page.goto(`${origin}/e2e/hatchery-discovery-fixture.html${query}`);
  await expect(page.getByRole('heading', { name: 'Hatchery', exact: true })).toBeVisible();
  return { errors, mutations, external, unexpectedApi };
}

async function capture(page, info, name) {
  const root = process.env.ABBY_DISCOVERY_CAPTURE_DIR;
  const destination = root ? path.join(root, name) : info.outputPath(name);
  await mkdir(path.dirname(destination), { recursive: true });
  await page.screenshot({ path: destination, fullPage: true });
  info.annotations.push({ type: 'capture', description: destination });
}
async function fits(region, page) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const geometry = await region.locator('button:visible, a:visible').evaluateAll((nodes) => nodes.map((node) => {
    const rect = node.getBoundingClientRect(); return { label: node.getAttribute('aria-label') || node.textContent, left: rect.left, right: rect.right, height: rect.height };
  }));
  const width = page.viewportSize().width;
  for (const control of geometry) {
    expect(control.left, control.label).toBeGreaterThanOrEqual(-1);
    expect(control.right, control.label).toBeLessThanOrEqual(width + 1);
    expect(control.height, control.label).toBeGreaterThanOrEqual(44);
  }
}
function safe(reads) { expect(reads.errors).toEqual([]); expect(reads.mutations).toEqual([]); expect(reads.external).toEqual([]); expect(reads.unexpectedApi).toEqual([]); }

for (const viewport of [{ width: 320, height: 640 }, { width: 390, height: 844 }, { width: 1280, height: 900 }]) {
  test(`empty inventory: actual Hatchery browsing and keyboard controls fit ${viewport.width}px`, async ({ page }, info) => {
    await page.setViewportSize(viewport);
    const reads = await open(page), region = page.getByRole('region', { name: 'Explore companions' });
    const control = region.getByRole('combobox', { name: 'Explore a family' });
    await expect(control).toContainText('Chick');
    await expect(region.getByRole('button', { name: 'Base appearance', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(region.getByRole('heading', { name: 'Explore companions', exact: true })).toBeInViewport();
    const discoveryTop = (await region.boundingBox()).y;
    const recipeTop = (await page.getByRole('heading', { name: 'Incubate a new pet', exact: true }).boundingBox()).y;
    expect(discoveryTop).toBeLessThan(recipeTop);
    await capture(page, info, `hatchery-discovery-initial-${viewport.width}.png`);
    await control.focus(); await control.press('End'); await control.press('Enter');
    await expect(control).toContainText(familyRows.at(-1).name); await expect(control).toBeFocused();
    await chooseDropdown(control, 'meshtint-dragon');
    const fire = region.getByRole('button', { name: 'Fire appearance', exact: true });
    await fire.focus(); await fire.press('Space'); await expect(fire).toHaveAttribute('aria-pressed', 'true');
    for (const [stage, name] of [['Baby', 'Fire Dragonling'], ['Middle', 'Fire Dragon'], ['Grown', 'Fire Elder Dragon']]) {
      await region.getByRole('button', { name: stage, exact: true }).click();
      await expect(region.getByRole('heading', { name, exact: true })).toBeVisible();
    }
    if (!installedExpansion) {
      await expect(region.getByText('Fire artwork is not available yet. You can still inspect the growth stages and choose your ingredients.')).toBeVisible();
      await expect(region.getByRole('button', { name: 'Show 3D preview', exact: true })).toHaveCount(0);
    }
    await fits(region, page); await capture(page, info, `hatchery-discovery-empty-${viewport.width}.png`);
    await chooseDropdown(control, 'meshtint-bee');
    await expect(region.getByRole('button', { name: 'Fire appearance', exact: true })).toHaveCount(0);
    await chooseDropdown(control, 'meshtint-bat');
    await expect(region.getByRole('button', { name: 'Ice appearance', exact: true })).toHaveCount(0);
    await expect(page.locator('canvas')).toHaveCount(0);
    await expect(page.getByText(/No eggs or potions for new hatching yet/)).toBeVisible();
    safe(reads);
  });
}

test('the ingredients shortcut reaches exact owned supplies without changing the browse selection or starting incubation', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 640 });
  const reads = await open(page, { mode: 'supplies' }), region = page.getByRole('region', { name: 'Explore companions' });
  const jump = page.getByRole('link', { name: 'Choose ingredients for incubation', exact: true });
  await expect(jump).toBeVisible();
  expect((await jump.boundingBox()).height).toBeGreaterThanOrEqual(44);
  const href = await jump.getAttribute('href');
  expect(href).toMatch(/^#.+/);
  expect(await page.evaluate((hash) => document.getElementById(hash.slice(1))?.contains(document.querySelector('[aria-label="Your eggs"]')), href)).toBe(true);
  await jump.click();
  const eggs = page.getByRole('region', { name: 'Your eggs', exact: true });
  await expect(eggs.getByRole('heading', { name: 'Your eggs', exact: true })).toBeInViewport();
  await expect(eggs.getByRole('button', { name: 'Select Mushroom Egg', exact: true })).toBeVisible();
  const eggControl = page.getByRole('combobox', { name: 'Egg', exact: true });
  const potionControl = page.getByRole('combobox', { name: 'Potion', exact: true });
  await chooseDropdown(eggControl, '501'); await chooseDropdown(potionControl, '601');
  await chooseDropdown(region.getByRole('combobox', { name: 'Explore a family' }), 'meshtint-dragon');
  await region.getByRole('button', { name: 'Ice appearance', exact: true }).click();
  await expect(eggControl).toContainText('Mushroom Egg'); await expect(potionControl).toContainText('Base Potion');
  await expect(page.getByRole('button', { name: 'Start incubation', exact: true })).toBeEnabled();
  await fits(region, page); await capture(page, info, 'hatchery-discovery-owned-ingredients.png');
  safe(reads);
});

test('saved pair states and frozen progress fit 150% text in the dark cover with reduced motion', async ({ page }, info) => {
  await page.setViewportSize({ width: 320, height: 640 }); await page.emulateMedia({ reducedMotion: 'reduce' });
  const reads = await open(page, { mode: 'mixed', query: '?theme=vigil&text=150' });
  const region = page.getByRole('region', { name: 'Explore companions' });
  await chooseDropdown(region.getByRole('combobox', { name: 'Explore a family' }), 'meshtint-mushroom');
  const status = region.getByRole('status', { name: 'Appearance collection status' });
  await expect(status).toHaveText('Owned'); await expect(region.getByText('2 of 3 appearances collected')).toBeVisible();
  await region.getByRole('button', { name: 'Fire appearance', exact: true }).click();
  await expect(status).toHaveText('Owned');
  await expect(region.getByRole('progressbar', { name: 'Saved Ember Grove progress' })).toHaveAttribute('aria-valuenow', '7');
  await expect(region.getByRole('progressbar', { name: 'Saved Ember Grove progress' })).toHaveAttribute('aria-valuemax', '12');
  const link = region.getByRole('link', { name: 'View Saved Ember Grove', exact: true });
  await expect(link).toHaveAttribute('href', savedPath);
  await region.getByRole('button', { name: 'Middle', exact: true }).click();
  await expect(region.getByRole('heading', { name: 'Fire Fungi', exact: true })).toBeVisible();
  await fits(region, page); await capture(page, info, 'hatchery-discovery-dark-150-reduced.png');
  expect(await page.evaluate(() => getComputedStyle(document.documentElement).fontSize)).toBe('24px');
  await region.getByRole('button', { name: 'Ice appearance', exact: true }).click();
  await expect(status).toHaveText('Incubating');
  await expect(region.getByRole('heading', { name: 'Ice Fungi', exact: true })).toBeVisible();
  await expect(page.locator('canvas')).toHaveCount(0);
  safe(reads);
});

test('a failed catalog remains retryable while a saved ready hatch stays available', async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let unavailable = true;
  const reads = await open(page, { mode: 'ready', catalogUnavailable: () => unavailable });
  const region = page.getByRole('region', { name: 'Explore companions' });
  await expect(page.getByRole('alert')).toContainText('Companion catalog temporarily unavailable');
  await expect(region.getByRole('status')).toContainText('appearances are unavailable');
  await expect(page.getByRole('button', { name: 'Hatch pet', exact: true })).toBeEnabled();
  await capture(page, info, 'hatchery-discovery-catalog-error-ready.png');
  unavailable = false; await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(region.getByRole('combobox', { name: 'Explore a family' })).toBeEnabled();
  await region.getByRole('button', { name: 'Fire appearance', exact: true }).click();
  await expect(region.getByRole('status', { name: 'Appearance collection status' })).toHaveText('Ready to hatch');
  await expect(page.getByRole('button', { name: 'Hatch pet', exact: true })).toBeEnabled();
  await fits(region, page); await capture(page, info, 'hatchery-discovery-ready-after-retry.png');
  safe(reads);
});

test('an inventory-free projected egg renders the exact Fire Dragon Middle idle through the real 3D preview', async ({ page }, info) => {
  test.skip(!installedExpansion, 'Exact private release absent: public UI checks exercise explicit unavailable-art presentation instead.');
  await page.setViewportSize({ width: 390, height: 844 });
  const requests = [];
  page.on('request', (request) => { if (request.url().endsWith('.glb')) requests.push(request.url()); });
  const reads = await open(page), region = page.getByRole('region', { name: 'Explore companions' });
  await chooseDropdown(region.getByRole('combobox', { name: 'Explore a family' }), 'meshtint-dragon');
  await region.getByRole('button', { name: 'Fire appearance', exact: true }).click();
  await region.getByRole('button', { name: 'Middle', exact: true }).click();
  await region.getByRole('button', { name: 'Show 3D preview', exact: true }).click();
  await page.locator('canvas').scrollIntoViewIfNeeded();
  const playback = region.getByRole('status', { name: 'Family preview playback', exact: true });
  await expect(playback).toHaveAttribute('data-playback-status', 'idle', { timeout: 45000 });
  await expect(playback).toHaveAttribute('data-stage', 'middle');
  await expect(playback).toHaveAttribute('data-variant-id', 'source-fly-idle');
  const binding = expansionManifest.appearance_bindings.stages.find((entry) => entry.species_slug === 'meshtint-dragon'
    && entry.potion_slug === 'fire' && entry.lifecycle_stage === 'middle' && entry.motion === 'idle');
  const file = expansionManifest.assets.find((asset) => asset.id === binding.asset_id).variants.find((variant) => variant.id === binding.variant_id).file;
  expect(requests.some((url) => url.endsWith(file))).toBe(true);
  await expect(page.locator('canvas')).toHaveCount(1);
  await fits(region, page); await capture(page, info, 'hatchery-discovery-projected-fire-dragon-middle-3d.png');
  await region.getByRole('button', { name: 'Use portrait', exact: true }).click();
  await expect(page.locator('canvas')).toHaveCount(0);
  safe(reads);
});

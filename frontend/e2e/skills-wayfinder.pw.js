import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;

const categories = [
  { id: 1, name: 'Woodworking', icon: '🪵', description: 'Working with wood' },
  { id: 2, name: 'Outdoors', icon: '🌿', description: 'Outdoor projects and nature' },
  { id: 3, name: 'Making & Fabrication', icon: '🔨', description: '3D printing, enclosure building, shop tools, hardware hacks' },
];
const subjects = [
  { id: 10, category: 1, name: 'Shop Basics', icon: '🔨' },
  { id: 11, category: 1, name: 'Advanced Technique', icon: '🪚' },
  { id: 20, category: 2, name: 'Field Skills', icon: '🧭' },
  { id: 30, category: 3, name: 'Shop Safety & Tools', icon: '🥽' },
  { id: 31, category: 3, name: 'Digital Fab', icon: '📐' },
];
const skills = [
  {
    id: 101, category: 1, subject: 10, name: 'Hand Tools', icon: '🪚',
    unlocked: true, level: 3, xp_points: 740, prerequisites: [],
    level_names: { 1: 'Sawdust Maker', 2: 'Handy', 3: 'Skilled', 4: 'Artisan', 5: 'Old School Master' },
  },
  {
    id: 102, category: 1, subject: 10, name: 'Measuring & Marking', icon: '📐',
    unlocked: true, level: 2, xp_points: 450, prerequisites: [],
    level_names: { 1: 'Eyeballer', 2: 'Precise', 3: 'Dead-On', 4: 'Master Measurer', 5: 'Micron Maniac' },
  },
  {
    id: 103, category: 1, subject: 11, name: 'Joinery', icon: '🔗',
    unlocked: true, level: 1, xp_points: 180,
    prerequisites: [
      { skill_id: 101, skill_name: 'Hand Tools', required_level: 3, met: true },
      { skill_id: 102, skill_name: 'Measuring & Marking', required_level: 2, met: true },
    ],
    level_names: { 1: 'Glue & Pray', 2: 'Butt Joints', 3: 'Dado & Rabbet', 4: 'Dovetailer', 5: 'Mortise Master' },
  },
  {
    id: 201, category: 2, subject: 20, name: 'Building & Construction', icon: '🏗️',
    unlocked: true, level: 0, xp_points: 0,
    prerequisites: [{ skill_id: 102, skill_name: 'Measuring & Marking', required_level: 2, met: true }],
    level_names: { 1: 'Stacker', 2: 'Leveler', 3: 'Framer', 4: 'Builder', 5: 'Architect' },
  },
  {
    id: 301, category: 3, subject: 30, name: 'Tool Mastery', icon: '🛠️',
    unlocked: true, level: 0, xp_points: 0, prerequisites: [],
    level_names: { 1: 'Tool Finder', 2: 'Right Tool Picker', 3: 'Handy', 4: 'Multi-Tool Master', 5: 'Tool Whisperer' },
  },
  {
    id: 302, category: 3, subject: 31, name: 'CAD & Modeling', icon: '📐',
    unlocked: false, level: 0, xp_points: 0,
    prerequisites: [{ skill_id: 301, skill_name: 'Tool Mastery', required_level: 2, met: false }],
    level_names: { 1: 'Sketcher', 2: 'Extruder', 3: 'Parametric', 4: 'Assembly Builder', 5: 'CAD Wizard' },
  },
];

function treeFor(categoryId) {
  return {
    category: categories.find((entry) => entry.id === categoryId),
    summary: { level: categoryId === 1 ? 3 : 0, total_xp: categoryId === 1 ? 1370 : 0 },
    subjects: subjects.filter((entry) => entry.category === categoryId).map((subject) => ({
      ...subject,
      skills: skills.filter((entry) => entry.subject === subject.id),
    })),
  };
}

test.beforeAll(async () => {
  // Serve production UI against intercepted synthetic reads only. Keep the
  // local fixture server's environment free of app and account credentials.
  devServer = spawn(process.execPath, [
    fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)),
    '--host', '127.0.0.1', '--port', '0',
  ], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  origin = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Vite fixture startup timed out: ${output}`)), 30_000);
    devServer.once('error', (error) => { clearTimeout(timer); reject(error); });
    devServer.once('exit', (code) => { clearTimeout(timer); reject(new Error(`Vite exited (${code}): ${output}`)); });
    devServer.stdout.on('data', (chunk) => {
      output += stripVTControlCharacters(chunk.toString());
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) { clearTimeout(timer); resolve(match[0]); }
    });
    devServer.stderr.on('data', (chunk) => { output += chunk.toString(); });
  });
});

test.afterAll(async () => {
  if (devServer && devServer.exitCode === null) {
    const stopped = once(devServer, 'exit');
    devServer.kill();
    await stopped;
  }
});

async function installCatalog(page) {
  const requests = [];
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (!path.startsWith('/api/')) return route.continue();
    requests.push({ method: request.method(), path, authorization: request.headers().authorization });
    const selectedTree = path.match(/^\/api\/skills\/tree\/(\d+)\/$/);
    const data = path === '/api/categories/' ? categories
      : path === '/api/subjects/' ? subjects
        : path === '/api/skills/' ? skills
          : selectedTree ? treeFor(Number(selectedTree[1])) : null;
    await route.fulfill({
      status: data ? 200 : 404,
      contentType: 'application/json',
      body: JSON.stringify(data || { detail: 'Unexpected fixture request' }),
    });
  });
  return requests;
}

async function expectDestination(page, name) {
  const heading = page.getByRole('heading', { level: 2, name, exact: true });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
}

async function expectGeometry(page, width) {
  await page.evaluate(() => document.fonts.ready);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  const buttons = page.getByRole('button');
  for (let index = 0; index < await buttons.count(); index += 1) {
    const button = buttons.nth(index);
    const bounds = await button.boundingBox();
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    // Decorative branch pseudo-elements intentionally extend past the button.
    // Measure real label content to catch clipping without counting branches.
    expect(await button.evaluate((element) => {
      const range = document.createRange();
      range.selectNodeContents(element);
      const buttonBounds = element.getBoundingClientRect();
      return [...range.getClientRects()].every((rect) => rect.left >= buttonBounds.left - 1 && rect.right <= buttonBounds.right + 1);
    })).toBe(true);
  }
  const labelIntersections = await page.locator('.wayfinder-skill-node').evaluateAll((nodes) => nodes.flatMap((node) => {
    const title = node.children[1]?.firstElementChild?.firstElementChild;
    const level = node.children[2];
    const chevron = node.children[3];
    if (!title || !level) return [];
    const range = document.createRange();
    range.selectNodeContents(title);
    const textRects = [...range.getClientRects()];
    const overlaps = [level, chevron].filter(Boolean).some((sibling) => {
      const bounds = sibling.getBoundingClientRect();
      return textRects.some((rect) => rect.left < bounds.right && rect.right > bounds.left
        && rect.top < bounds.bottom && rect.bottom > bounds.top);
    });
    return overlaps ? [{ title: title.textContent, viewport: window.innerWidth }] : [];
  }));
  expect(labelIntersections, 'Full skill labels must not overlap their level or chevron').toEqual([]);
}

async function returnToOverview(page) {
  await page.getByRole('navigation', { name: 'Skill navigation' }).getByRole('button', { name: 'All skills', exact: true }).click();
  await expectDestination(page, 'Your skills');
}

for (const width of [320, 375, 768, 1280]) {
  test(`Wayfinder drilldown fits a ${width}px viewport and follows real prerequisite paths`, async ({ page }) => {
    const requests = await installCatalog(page);
    await page.setViewportSize({ width, height: 740 });
    await page.goto(`${origin}/e2e/skills-wayfinder-fixture.html`);
    await expect(page.getByRole('heading', { level: 2, name: 'Your skills' })).toBeVisible();
    const making = page.getByRole('button', { name: 'Making & Fabrication, 2 subjects · 2 skills' });
    await expect(making).toHaveText('🔨Making & Fabrication2 subjects · 2 skills');
    await expectGeometry(page, width);
    await making.click();
    await expectDestination(page, 'Making & Fabrication');
    await expect(page.getByRole('button', { name: 'Shop Safety & Tools, 1 skill' })).toBeVisible();
    await expectGeometry(page, width);
    await page.getByRole('button', { name: 'Back', exact: true }).click();
    await expectDestination(page, 'Your skills');

    await page.getByRole('button', { name: 'Woodworking, 2 subjects · 3 skills' }).click();
    await expectDestination(page, 'Woodworking');
    await expectGeometry(page, width);
    await page.getByRole('button', { name: 'Advanced Technique, 1 skill' }).click();
    await expectDestination(page, 'Advanced Technique');
    const joinery = page.getByRole('button', { name: /Joinery, level 1/ });
    await expect(joinery).toHaveText(/Joinery/);
    await expectGeometry(page, width);
    await joinery.click();
    await expectDestination(page, 'Joinery');
    await expect(page.getByText('Level 1 · Glue & Pray · 180 XP')).toBeVisible();
    await expectGeometry(page, width);
    await page.getByRole('button', { name: /Hand Tools.*Requires Level 3.*Met/ }).click();
    await expectDestination(page, 'Hand Tools');
    await expect(page.getByText('Level 3 · Skilled · 740 XP')).toBeVisible();
    await expectGeometry(page, width);
    await page.getByRole('button', { name: 'Back', exact: true }).click();
    await expectDestination(page, 'Joinery');
    await expect(page.getByText('Level 1 · Glue & Pray · 180 XP')).toBeVisible();
    await returnToOverview(page);

    await page.getByRole('button', { name: 'Outdoors, 1 subject · 1 skill' }).click();
    await expectDestination(page, 'Outdoors');
    await page.getByRole('button', { name: 'Field Skills, 1 skill' }).click();
    await expectDestination(page, 'Field Skills');
    const construction = page.getByRole('button', { name: /Building & Construction, level 0/ });
    await expect(construction).toHaveText(/Building & Construction/);
    await expectGeometry(page, width);
    await construction.click();
    await expectDestination(page, 'Building & Construction');
    const measuring = page.getByRole('button', { name: /Measuring & Marking.*Woodworking.*Requires Level 2.*Met/ });
    await expect(measuring).toBeVisible();
    await expectGeometry(page, width);
    await measuring.click();
    await expectDestination(page, 'Measuring & Marking');
    await expect(page.getByText('Level 2 · Precise · 450 XP')).toBeVisible();
    await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
    await expectGeometry(page, width);
    await page.getByRole('button', { name: 'Back', exact: true }).click();
    await expectDestination(page, 'Building & Construction');
    await expect(page.getByText('Level 0 · 0 XP', { exact: true })).toBeVisible();
    await returnToOverview(page);
    expect(requests.every((request) => request.method === 'GET' && request.authorization === undefined)).toBe(true);
  });
}

test('Wayfinder follows the dark cover and reduced-motion setting', async ({ page }) => {
  await installCatalog(page);
  await page.setViewportSize({ width: 375, height: 740 });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
  await page.goto(`${origin}/e2e/skills-wayfinder-fixture.html?theme=vigil`);
  await expect(page.getByRole('button', { name: 'Woodworking, 2 subjects · 3 skills' })).toBeVisible();
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(41, 37, 56)');
  const marker = page.locator('.wayfinder-marker').first();
  await expect(marker).toHaveCSS('background-color', 'rgb(61, 52, 80)');
  await expect(marker).toHaveCSS('transition-duration', '0s');
  await expectGeometry(page, 375);
  await page.getByRole('button', { name: 'Woodworking, 2 subjects · 3 skills' }).click();
  await expectDestination(page, 'Woodworking');
  await page.getByRole('button', { name: 'Shop Basics, 2 skills' }).click();
  await expectDestination(page, 'Shop Basics');
  const measuring = page.getByRole('button', { name: /Measuring & Marking, level 2/ });
  await expect(measuring).toHaveCSS('opacity', '1');
  await expect(measuring).toHaveCSS('transform', 'none');
  await expectGeometry(page, 375);
  await measuring.click();
  await expectDestination(page, 'Measuring & Marking');
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
  await expectGeometry(page, 375);
});

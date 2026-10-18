import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';

let devServer;
let origin;
let metadata;
let report;
let economyReport;
let budgetReport;

test.beforeAll(async () => {
  metadata = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-metadata.json', import.meta.url), 'utf8'));
  report = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-report.json', import.meta.url), 'utf8'));
  economyReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-economy-report.json', import.meta.url), 'utf8'));
  budgetReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-reward-budget-report.json', import.meta.url), 'utf8'));
  devServer = spawn(process.execPath, [fileURLToPath(new URL('../node_modules/vite/bin/vite.js', import.meta.url)), '--host', '127.0.0.1', '--port', '0'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    env: Object.fromEntries(Object.entries(process.env).filter(([key]) => /^(PATH|SYSTEMROOT|WINDIR|TEMP|TMP|HOME|USERPROFILE)$/i.test(key))),
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  origin = await new Promise((resolve, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(new Error(`Fixture startup timed out: ${output}`)), 30_000);
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

async function openLab(page, response = report) {
  const requests = [];
  const external = [];
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-progression-fixture'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    requests.push(url.pathname);
    if (url.pathname === '/api/auth/me/') return route.fulfill({ json: { id: 1, username: 'synthetic-staff', role: 'parent', is_staff: true, theme: 'hyrule', family: { id: 1 } } });
    if (url.pathname === '/api/rpg/progression-lab/') return route.fulfill({ json: { ...metadata, defaults: response.config } });
    if (url.pathname === '/api/rpg/progression-lab/simulate/') {
      expect(route.request().postDataJSON()).toEqual(response.config);
      return route.fulfill({ json: response });
    }
    return route.fulfill({ status: 403, json: { detail: 'No household APIs in this fixture.' } });
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/progression-lab-fixture.html`);
  await expect(page.getByRole('button', { name: 'Run simulation', exact: true })).toBeVisible();
  return { requests, external };
}

for (const width of [375, 1280]) {
  test(`per-child reward budget comparison remains readable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page, budgetReport);
    await expect(page.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveValue('5');
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    const forecast = page.getByRole('region', { name: 'Reward budget forecast', exact: true });
    await expect(forecast.getByRole('table', { name: 'Reward budget totals across simulated journeys' })).toBeVisible();
    await expect(forecast.getByRole('rowheader', { name: 'Coins omitted by the budget' })).toBeVisible();
    await page.getByRole('button', { name: 'Keep as comparison' }).click();
    await expect(forecast.getByText(/Comparison budget: 5 Coins/)).toBeVisible();
    await page.getByRole('button', { name: '100 Coins per child per day', exact: true }).click();
    await expect(page.getByText(/Inputs have changed/)).toBeVisible();
    await expect(page.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveValue('100');
    expect(requests.filter((path) => path.endsWith('/simulate/'))).toHaveLength(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.every((path) => ['/api/auth/me/', '/api/rpg/progression-lab/', '/api/rpg/progression-lab/simulate/'].includes(path))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progression-budget-${width}.png`), fullPage: true });
  });

  test(`purchasing forecasts separate Coins and money at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page, economyReport);
    await expect(page.getByRole('checkbox', { name: 'Model purchases and family costs' })).toBeChecked();
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    const purchasing = page.getByRole('region', { name: 'Purchasing forecast' });
    await expect(purchasing).toBeVisible();
    await expect(purchasing.getByRole('table', { name: 'Affordability and actual purchases for each reward' })).toBeVisible();
    await expect(purchasing.getByRole('table', { name: 'Calendar month purchasing results, median per child' })).toBeVisible();
    await expect(purchasing.getByRole('rowheader', { name: /^Practice outing/ })).toBeVisible();
    await expect(purchasing.getByRole('rowheader', { name: /^Practice print/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.filter((path) => path.endsWith('/simulate/'))).toHaveLength(1);
    expect(requests.every((path) => ['/api/auth/me/', '/api/rpg/progression-lab/', '/api/rpg/progression-lab/simulate/'].includes(path))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progression-economy-${width}.png`), fullPage: true });
  });

  test(`designer report is readable at ${width}px without horizontal page overflow`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page);
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    await expect(page.getByRole('region', { name: 'Simulation report' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Model coverage and audit' })).toBeVisible();
    const slider = page.getByRole('slider', { name: 'Inspect calendar day' });
    await slider.focus();
    await page.keyboard.press('ArrowRight');
    await expect(slider).toHaveValue('1');
    await expect(slider).toHaveAccessibleDescription(`Day ${report.trace[1].day}`);
    await page.getByRole('button', { name: 'Keep as comparison' }).click();
    await expect(page.getByRole('table', { name: 'Milestone completion and calendar days among successful journeys' }).getByRole('columnheader', { name: 'Comparison median' })).toBeVisible();
    for (const name of ['Sources: mean totals per simulated child', 'Sinks and consumption: mean totals per simulated child']) {
      const table = page.getByRole('table', { name });
      if (await table.count()) await expect(table).toBeVisible();
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.every((path) => ['/api/auth/me/', '/api/rpg/progression-lab/', '/api/rpg/progression-lab/simulate/'].includes(path))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progression-lab-${width}.png`), fullPage: true });
  });
}

test('unreached milestones and empty flows remain honest and keyboard controls work', async ({ page }) => {
  const empty = { ...report,
    milestones: report.milestones.map((entry) => ({ ...entry, completion_rate: 0, completed_trials: 0, p10_days: null, p50_days: null, p90_days: null })),
    flows: { sources: [], sinks: [] },
  };
  const { requests } = await openLab(page, empty);
  const horizon = page.getByRole('combobox', { name: 'Forecast horizon' });
  await horizon.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('listbox')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(horizon).toBeFocused();
  await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'Not reached', exact: true })).toHaveCount(report.milestones.length * 3);
  await expect(page.getByText('No modeled entries.', { exact: true })).toHaveCount(2);
  await expect(page.getByRole('cell', { name: 'Day 0', exact: true })).toHaveCount(0);
  await page.getByText('Load a saved routine', { exact: true }).click();
  await page.getByLabel('Saved routine', { exact: true }).setInputFiles({
    name: 'exported-routine.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ ...report, config: { ...report.config, seed: report.config.seed + 1 } })),
  });
  await expect(page.getByText(/Saved routine loaded/)).toBeVisible();
  await expect(page.getByRole('spinbutton', { name: 'Random seed' })).toHaveValue(String(report.config.seed + 1));
  await expect(page.getByText(/Inputs have changed/)).toBeVisible();
  expect(requests.filter((path) => path.endsWith('/simulate/'))).toHaveLength(1);
});

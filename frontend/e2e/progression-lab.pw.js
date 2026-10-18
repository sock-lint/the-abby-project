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
let discoveryReport;

const allowedApiRequests = new Set([
  'GET /api/auth/me/',
  'GET /api/rpg/progression-lab/',
  'GET /api/challenges/discovery/',
  'POST /api/rpg/progression-lab/simulate/',
]);

function assertApiIsolation(requests) {
  expect(requests.every(({ method, path }) => allowedApiRequests.has(`${method} ${path}`))).toBe(true);
  for (const request of requests) {
    if (request.method === 'GET') {
      expect(request.body).toBeNull();
      expect(request.query.filter((key) => !['_abby_session', '_abby_retry'].includes(key))).toEqual([]);
    } else {
      // The only allowed POST is the anonymous simulation. Discovery stays a
      // separate read; no household targeting or observations enter its URL.
      expect(request.path).toBe('/api/rpg/progression-lab/simulate/');
      expect(request.query).toEqual([]);
    }
  }
}

test.beforeAll(async () => {
  metadata = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-metadata.json', import.meta.url), 'utf8'));
  report = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-report.json', import.meta.url), 'utf8'));
  economyReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-economy-report.json', import.meta.url), 'utf8'));
  budgetReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-reward-budget-report.json', import.meta.url), 'utf8'));
  discoveryReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/challenge-discovery-observed.json', import.meta.url), 'utf8'));
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

async function openLab(page, response = report, discovery = discoveryReport) {
  const requests = [];
  const external = [];
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-progression-fixture'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    requests.push({ method: route.request().method(), path: url.pathname,
      body: route.request().postData(), query: [...url.searchParams.keys()] });
    if (url.pathname === '/api/auth/me/') return route.fulfill({ json: { id: 1, username: 'synthetic-staff', role: 'parent', is_staff: true, theme: 'hyrule', family: { id: 1 } } });
    if (url.pathname === '/api/rpg/progression-lab/') return route.fulfill({ json: { ...metadata, defaults: response.config } });
    if (url.pathname === '/api/challenges/discovery/') return route.fulfill({ json: discovery });
    if (url.pathname === '/api/rpg/progression-lab/simulate/') {
      expect(route.request().postDataJSON()).toEqual(response.config);
      return route.fulfill({ json: response });
    }
    return route.fulfill({ status: 403, json: { detail: 'No household APIs in this fixture.' } });
  });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto(`${origin}/e2e/progression-lab-fixture.html`);
  await expect(page.getByRole('button', { name: 'Run simulation', exact: true })).toBeVisible();
  const panel = page.getByRole('region', { name: 'Recorded challenge discovery', exact: true });
  if (discovery.status === 'observations_available') {
    await expect(panel.getByRole('definition')).toHaveText([
      discovery.catalog_occurrences.cohort_materialized, discovery.catalog_occurrences.opened,
      discovery.catalog_occurrences.completed, discovery.catalog_occurrences.completed_without_recorded_opening,
    ].map(String));
    await expect(panel.getByText(/Opening details does not establish that a child read or enjoyed them/)).toBeVisible();
    await expect(panel.getByText(/Windows created by the server are not screen impressions/)).toBeVisible();
    await panel.getByText('Discovery coverage and accounting', { exact: true }).click();
    await expect(panel.getByText(`${discovery.cohort.tracked_children} tracked children · ${discovery.cohort.untracked_children} with unknown earlier opening history.`, { exact: true })).toBeVisible();
    await expect(panel.getByText(`${discovery.catalog_occurrences.opened_and_completed} windows both opened and completed. ${discovery.catalog_occurrences.opening_recorded_after_completion} first openings were recorded after completion. These groups overlap the totals above.`, { exact: true })).toBeVisible();
  } else {
    await expect(panel.getByRole('status')).toHaveText(discovery.status === 'insufficient_evidence'
      ? 'No tracked challenge windows in this new-user cohort yet.'
      : 'Observation capacity was exceeded. Counts are unavailable; no partial sample is shown.');
    await expect(panel.getByRole('definition')).toHaveCount(0);
  }
  expect(requests.filter(({ path }) => path === '/api/challenges/discovery/')).toHaveLength(1);
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
    expect(requests.filter(({ path }) => path.endsWith('/simulate/'))).toHaveLength(1);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    assertApiIsolation(requests);
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
    expect(requests.filter(({ path }) => path.endsWith('/simulate/'))).toHaveLength(1);
    assertApiIsolation(requests);
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
    assertApiIsolation(requests);
    await page.screenshot({ path: testInfo.outputPath(`progression-lab-${width}.png`), fullPage: true });
  });
}

test('unreached milestones and empty flows remain honest and keyboard controls work', async ({ page }) => {
  const empty = { ...report,
    milestones: report.milestones.map((entry) => ({ ...entry, completion_rate: 0, completed_trials: 0, p10_days: null, p50_days: null, p90_days: null })),
    flows: { sources: [], sinks: [] },
  };
  const { requests, external } = await openLab(page, empty);
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
  expect(requests.filter(({ path }) => path.endsWith('/simulate/'))).toHaveLength(1);
  expect(external).toEqual([]);
  assertApiIsolation(requests);
});

for (const status of ['insufficient_evidence', 'cohort_limit_exceeded', 'occurrence_limit_exceeded']) {
  test(`discovery ${status} does not present unknown evidence as zero or mutate household state`, async ({ page }) => {
    const limited = status !== 'insufficient_evidence';
    const discovery = { ...discoveryReport, status,
      cohort: { ...discoveryReport.cohort, truncated: limited,
        eligible_children: status === 'cohort_limit_exceeded' ? null : discoveryReport.cohort.eligible_children,
        tracked_children: limited ? null : discoveryReport.cohort.tracked_children,
        untracked_children: limited ? null : discoveryReport.cohort.untracked_children },
      catalog_occurrences: Object.fromEntries(Object.keys(discoveryReport.catalog_occurrences).map((key) => [key, limited ? null : 0])),
    };
    const { requests, external } = await openLab(page, report, discovery);
    expect(requests.every(({ method }) => method === 'GET')).toBe(true);
    expect(external).toEqual([]);
    assertApiIsolation(requests);
  });
}

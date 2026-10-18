import { test, expect } from '@playwright/test';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { stripVTControlCharacters } from 'node:util';
import { chooseDropdown } from './dropdown-helpers.js';

let devServer;
let origin;
let metadata;
let report;
let economyReport;
let budgetReport;
let commitmentReport;
let expeditionReport;
let expeditionComparison;
let experimentList;
let experimentComparison;
let experimentDecided;
let emptyObservations;
const labReads = ['/api/auth/me/', '/api/rpg/progression-lab/', '/api/rpg/progression-lab/simulate/', '/api/rpg/progression-lab/experiments/', '/api/rpg/progression-lab/observations/'];

test.beforeAll(async () => {
  metadata = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-metadata.json', import.meta.url), 'utf8'));
  report = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-report.json', import.meta.url), 'utf8'));
  economyReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-economy-report.json', import.meta.url), 'utf8'));
  budgetReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-reward-budget-report.json', import.meta.url), 'utf8'));
  commitmentReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-commitment-report.json', import.meta.url), 'utf8'));
  expeditionReport = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-lab-expedition-budget-report.json', import.meta.url), 'utf8'));
  expeditionComparison = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-experiment-expedition-budget-comparison.json', import.meta.url), 'utf8'));
  experimentList = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-experiment-list.json', import.meta.url), 'utf8'));
  experimentComparison = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-experiment-comparison.json', import.meta.url), 'utf8'));
  experimentDecided = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-experiment-decided.json', import.meta.url), 'utf8'));
  emptyObservations = JSON.parse(await readFile(new URL('../../contracts/api/fixtures/progression-observations-empty.json', import.meta.url), 'utf8'));
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

async function openLab(page, response = report, quotaExperiment = false) {
  const evidence = quotaExperiment ? expeditionComparison : experimentComparison;
  const requests = [];
  const external = [];
  let savedExperiment = null;
  const experimentRoot = '/api/rpg/progression-lab/experiments/';
  const experimentPath = `${experimentRoot}${experimentDecided.id}/`;
  await page.addInitScript(() => localStorage.setItem('abby_auth_token', 'synthetic-progression-fixture'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== origin) { external.push(url.origin); return route.abort(); }
    if (!url.pathname.startsWith('/api/')) return route.continue();
    requests.push(url.pathname);
    if (url.pathname === '/api/auth/me/') return route.fulfill({ json: { id: 1, username: 'synthetic-staff', role: 'parent', is_staff: true, theme: 'hyrule', family: { id: 1 } } });
    if (url.pathname === '/api/rpg/progression-lab/') return route.fulfill({ json: { ...metadata, defaults: response.config } });
    if (url.pathname === '/api/rpg/progression-lab/observations/') return route.fulfill({ json: emptyObservations });
    if (url.pathname === experimentRoot && route.request().method() === 'GET') return route.fulfill({ json: experimentList });
    if (url.pathname === experimentRoot && route.request().method() === 'POST') {
      const input = route.request().postDataJSON();
      expect(Object.keys(input).sort()).toEqual(['candidate_daily_coins', 'candidate_expedition_budget', 'candidate_policy', 'config', 'hypothesis', 'name', 'targets']);
      if (quotaExperiment) {
        expect(input.config).toEqual(evidence.control.config);
        expect(input.candidate_policy).toBe('expedition_limits');
        expect(input.candidate_daily_coins).toBeNull();
        expect(input.candidate_expedition_budget).toEqual(evidence.candidate.config.expedition_budget);
      } else {
        expect(input.config).toEqual({ ...response.config, reward_budget: { daily_coins: null }, reward_commitment: { enabled: false }, expedition_budget: { daily_launches: null, daily_items: null } });
        expect(input.candidate_daily_coins).toBe(100);
      }
      savedExperiment = { ...experimentDecided, ...input, latest_decision: null, comparisons: [], decisions: [], observations: [] };
      return route.fulfill({ status: 201, json: savedExperiment });
    }
    if (url.pathname === experimentPath) return route.fulfill({ json: savedExperiment ?? experimentDecided });
    if (url.pathname === `${experimentPath}compare/`) {
      expect(route.request().postDataJSON()).toEqual({ revision: 1 });
      savedExperiment = { ...savedExperiment, comparisons: experimentDecided.comparisons };
      return route.fulfill({ status: 201, json: evidence });
    }
    if (url.pathname === `${experimentPath}comparisons/${experimentComparison.id}/`) return route.fulfill({ json: evidence });
    if (url.pathname === `${experimentPath}decisions/`) {
      const input = route.request().postDataJSON();
      expect(input).toEqual({ revision: 1, comparison_id: experimentComparison.id, outcome: 'keep_testing', rationale: 'Keep testing reward commitments.', next_action: 'Simulate the expedition table.', review_on: '2099-01-01' });
      savedExperiment = { ...experimentDecided, observations: savedExperiment?.observations ?? [] };
      return route.fulfill({ status: 201, json: savedExperiment });
    }
    if (url.pathname === `${experimentPath}observations/`) {
      expect(route.request().postDataJSON()).toEqual({ revision: 1 });
      savedExperiment = { ...savedExperiment, observations: [{ id: 'checkpoint-1', created_at: '2026-10-18T12:00:00Z', status: emptyObservations.status, payload: emptyObservations, binding: experimentComparison.binding, experiment_revision: 1 }] };
      return route.fulfill({ status: 201, json: savedExperiment });
    }
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
  test(`shared expedition limits preserve Coin rules and saved evidence at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page, expeditionReport, true);
    await expect(page.getByRole('checkbox', { name: 'Test the 100-Coin commitment prototype' })).toBeChecked();
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    const result = page.getByRole('region', { name: 'Simulation report', exact: true }).getByRole('region', { name: 'Expedition budget forecast' });
    await expect(result.getByRole('rowheader', { name: 'New item slots promised' })).toBeVisible();
    await expect(result.getByRole('rowheader', { name: 'Trips promising no Coins or items' })).toBeVisible();
    await page.getByRole('button', { name: 'Keep as comparison' }).click();
    await expect(result.getByRole('columnheader', { name: 'Comparison median' })).toBeVisible();
    const notebook = page.getByRole('region', { name: 'Progression experiment notebook', exact: true });
    await chooseDropdown(notebook.getByRole('combobox', { name: 'Candidate reward policy' }), 'expedition_limits');
    const candidate = notebook.getByRole('region', { name: 'Candidate expedition limits' });
    await expect(candidate.getByRole('spinbutton', { name: 'Daily expedition launches per child' })).toHaveValue('1');
    await expect(candidate.getByRole('spinbutton', { name: 'Daily expedition items per child' })).toHaveValue('1');
    await expect(notebook.getByRole('spinbutton', { name: 'Candidate Coins per child per day' })).toHaveCount(0);
    await notebook.getByRole('button', { name: 'Save experiment', exact: true }).click();
    await expect(notebook.getByText('Experiment saved. Live rewards are unchanged.')).toBeVisible();
    await notebook.getByRole('button', { name: 'Run control and candidate' }).click();
    const saved = notebook.getByRole('region', { name: 'Saved experiment comparison', exact: true });
    await expect(saved.getByText(/Control: 100-Coin commitment prototype.*Unlimited expeditions.*Candidate: 100-Coin commitment prototype/)).toBeVisible();
    await expect(saved.getByRole('region', { name: 'Expedition budget forecast' })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.every((path) => labReads.includes(path) || path.startsWith(`/api/rpg/progression-lab/experiments/${experimentDecided.id}/`))).toBe(true);
    await result.screenshot({ path: testInfo.outputPath(`progression-expedition-report-${width}.png`) });
    await candidate.screenshot({ path: testInfo.outputPath(`progression-expedition-controls-${width}.png`) });
    await page.screenshot({ path: testInfo.outputPath(`progression-expedition-limits-${width}.png`), fullPage: true });
  });

  test(`saved experiment closes the feedback loop at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page);
    const notebook = page.getByRole('region', { name: 'Progression experiment notebook', exact: true });
    await expect(notebook.getByRole('combobox', { name: 'Open experiment' })).toBeVisible();
    await notebook.getByRole('button', { name: 'Add criterion', exact: true }).click();
    await notebook.getByRole('spinbutton', { name: 'Criterion 1 minimum' }).fill('0');
    await notebook.getByRole('button', { name: 'Save experiment', exact: true }).click();
    await expect(notebook.getByText('Experiment saved. Live rewards are unchanged.')).toBeVisible();
    await notebook.getByRole('button', { name: 'Run control and candidate' }).click();
    await expect(notebook.getByRole('table', { name: 'Experiment success criteria' })).toBeVisible();
    await notebook.getByRole('textbox', { name: 'Decision reason' }).fill('Keep testing reward commitments.');
    await notebook.getByRole('textbox', { name: 'Next action', exact: true }).fill('Simulate the expedition table.');
    await notebook.getByLabel('Review on', { exact: true }).fill('2099-01-01');
    await notebook.getByRole('button', { name: 'Record decision' }).click();
    await expect(notebook.getByText('Decision recorded. No live changes were approved.')).toBeVisible();
    await notebook.getByRole('button', { name: 'Save observation checkpoint' }).click();
    await expect(notebook.getByText(/Observation checkpoint saved/)).toBeVisible();
    await notebook.getByRole('button', { name: 'Reload saved experiment' }).click();
    await expect(notebook.getByText('Saved experiment loaded.')).toBeVisible();
    await expect(notebook.getByText(experimentDecided.decisions[0].next_action)).toBeVisible();
    await chooseDropdown(notebook.getByRole('combobox', { name: 'Saved comparison' }), experimentComparison.id);
    await expect(notebook.getByRole('region', { name: 'Saved experiment comparison' })).toBeVisible();
    await expect(notebook.getByText(/Available as an opt-in Lab prototype/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.every((path) => labReads.includes(path) || path.startsWith(`/api/rpg/progression-lab/experiments/${experimentDecided.id}/`))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progression-feedback-${width}.png`), fullPage: true });
  });

  test(`commitment promises and outstanding rewards are readable at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const { requests, external } = await openLab(page, commitmentReport);
    await expect(page.getByRole('checkbox', { name: 'Test the 100-Coin commitment prototype' })).toBeChecked();
    await page.getByRole('button', { name: 'Run simulation', exact: true }).click();
    const results = page.getByRole('region', { name: 'Reward commitment forecast', exact: true });
    await expect(results.getByText('New Coins committed', { exact: true })).toBeVisible();
    await expect(results.getByText('Direct Coins awaiting claim', { exact: true })).toBeVisible();
    await expect(results.getByText(/Removing access is not additional content runway/)).toBeVisible();
    await results.getByText('Pouch promises by source', { exact: true }).click();
    await expect(results.getByRole('table', { name: 'Mean pouch Coins per child', exact: true })).toBeVisible();
    await results.getByText('Commitment model assumptions', { exact: true }).click();
    await expect(results.getByText(/Consumables and boosts/)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    expect(external).toEqual([]);
    expect(requests.every((path) => labReads.includes(path))).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`progression-commitments-${width}.png`), fullPage: true });
  });

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
    expect(requests.every((path) => labReads.includes(path))).toBe(true);
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
    expect(requests.every((path) => labReads.includes(path))).toBe(true);
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
    expect(requests.every((path) => labReads.includes(path))).toBe(true);
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

import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import ProgressionLab from './ProgressionLab';
import { renderWithProviders } from '../../test/render';
import { buildParent, buildUser } from '../../test/factories';
import { server } from '../../test/server';
import { spyHandler } from '../../test/spy';
import { useAuth } from '../../hooks/useApi';
import { selectDropdown } from '../../test/selectDropdown';
import sharedMetadata from '../../../../contracts/api/fixtures/progression-lab-metadata.json';
import sharedReport from '../../../../contracts/api/fixtures/progression-lab-report.json';
import sharedEconomyReport from '../../../../contracts/api/fixtures/progression-lab-economy-report.json';
import { economyDefaults, economyMetadata } from './progressionEconomyTestData';
import { formatCurrency } from '../../utils/format';

const defaults = {
  horizon_days: 90, trials: 20, seed: 42, active_days_per_week: 5,
  reading_minutes: 10, project_minutes: 0, chores_per_day: 2, chore_coins: 10,
  chore_xp: 10, habits_per_day: 1, habit_xp: 5, movement_sessions_per_day: 0,
  movement_minutes: 20, movement_intensity: 'medium', creations_per_day: 0,
  journal_per_day: true, feed_strategy: 'feed_all', expeditions_per_day: 1,
  expedition_tier: 'long',
};
const metadata = {
  schema_version: 1, defaults,
  limits: {
    horizon_days: { choices: [30, 90, 180, 365] }, trials: { min: 1, max: 40 }, seed: { min: 0, max: 2147483647 },
    active_days_per_week: { min: 1, max: 7 }, reading_minutes: { min: 0, max: 240 }, project_minutes: { min: 0, max: 240 },
    chores_per_day: { min: 0, max: 10 }, chore_coins: { min: 0, max: 200 }, chore_xp: { min: 0, max: 100 },
    habits_per_day: { min: 0, max: 10 }, habit_xp: { min: 0, max: 100 }, movement_sessions_per_day: { min: 0, max: 6 },
    movement_minutes: { min: 1, max: 240 }, movement_intensity: { choices: ['low', 'medium', 'high'] },
    creations_per_day: { min: 0, max: 4 }, feed_strategy: { choices: ['feed_all', 'none'] },
    journal_per_day: { type: 'boolean' },
    expeditions_per_day: { min: 0, max: 15 }, expedition_tier: { choices: ['short', 'standard', 'long'] },
  },
  catalog: { finite_total: 4 },
  coverage: { modeled: ['Reading rewards'], excluded: ['Private household shops'], assumptions: ['Approvals complete on the active day'] },
  audit: [{ severity: 'warning', code: 'test_fixture_only', message: 'Synthetic audit finding' }],
  presets: [{ name: 'Light', config: { ...defaults, active_days_per_week: 3 } }],
};
const report = {
  schema_version: 1, config: defaults, catalog: metadata.catalog, coverage: metadata.coverage, audit: metadata.audit,
  milestones: [
    { key: 'first_pet', label: 'First companion', completion_rate: 0.5, completed_trials: 10, trials: 20, p10_days: 8, p50_days: 14, p90_days: 20 },
    { key: 'all_pets', label: 'Every companion', completion_rate: 0, completed_trials: 0, trials: 20, p10_days: null, p50_days: null, p90_days: null },
  ],
  trace: [
    { day: 1, coins_p50: 20, total_xp_p50: 30, pets_p50: 0, mounts_p50: 0, finite_remaining_p50: 4, finite_completed_p50: 0 },
    { day: 90, coins_p50: 900, total_xp_p50: 1000, pets_p50: 1, mounts_p50: 0, finite_remaining_p50: 3, finite_completed_p50: 1 },
  ],
  summary: { finite_content_total: 4, finite_remaining_p50: 3, active_days: 65, longest_novelty_gap_p50: 21, expired_oneoff_challenges_p50: 0 },
  flows: { sources: [{ source: 'reading', coins: 100, xp: 150, items: 0 }], sinks: [{ source: 'feeding', coins: 0, xp: 0, items: 2 }] },
  journey: { seed: 42, events: [{ day: 1, source: 'reading', coins: 5, xp: 15, items: [] }], truncated: true },
};

function setupMetadata() {
  server.use(
    http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
    http.get('*/api/rpg/progression-lab/', () => HttpResponse.json(metadata)),
  );
}

describe('Progression lab', () => {
  it('compares shared launch and item limits while preserving Coin rules and routine presets', async () => {
    const current = { ...metadata, defaults: { ...defaults, reward_commitment: { enabled: true }, reward_budget: { daily_coins: null }, expedition_budget: { daily_launches: null, daily_items: null } }, expedition_budget_defaults: { daily_launches: null, daily_items: null }, expedition_budget_limits: { daily_launches: { min: 0, max: 15 }, daily_items: { min: 0, max: 45 } } };
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())), http.get('*/api/rpg/progression-lab/', () => HttpResponse.json(current)));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...report, config: body }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: '1 launch per child per day' }));
    await user.click(screen.getByRole('button', { name: 'Use light routine' }));
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('button', { name: 'Keep as comparison' });
    expect(simulation.calls[0].body).toMatchObject({ active_days_per_week: 3, reward_commitment: { enabled: true }, expedition_budget: { daily_launches: 1, daily_items: null } });
    await user.click(screen.getByRole('button', { name: '3 items per child per day' }));
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(2));
    expect(simulation.calls[1].body).toMatchObject({ reward_commitment: { enabled: true }, expedition_budget: { daily_launches: null, daily_items: 3 } });
  });
  it('switches policies explicitly and preserves the commitment choice through routine presets', async () => {
    const current = { ...metadata, defaults: { ...defaults, reward_budget: { daily_coins: null }, reward_commitment: { enabled: false } }, reward_budget_defaults: { daily_coins: null }, reward_budget_limits: { daily_coins: { min: 0, max: 100000, nullable: true } }, reward_commitment_defaults: { enabled: false } };
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())), http.get('*/api/rpg/progression-lab/', () => HttpResponse.json(current)));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...report, config: body }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: '100 Coins per child per day' }));
    const toggle = screen.getByRole('checkbox', { name: 'Test the 100-Coin commitment prototype' });
    await user.click(toggle);
    expect(screen.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveValue(null);
    await user.click(screen.getByRole('button', { name: 'Use light routine' }));
    expect(toggle).toBeChecked();
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('button', { name: 'Keep as comparison' });
    expect(simulation.calls[0].body).toMatchObject({ active_days_per_week: 3, reward_budget: { daily_coins: null }, reward_commitment: { enabled: true } });
    await user.click(screen.getByRole('button', { name: '50 Coins per child per day' }));
    expect(toggle).not.toBeChecked();
  });
  const incubationPolicy = { duration_seconds: 86400, max_active: 1, clock: 'elapsed_seconds',
    start_strategy: 'first_compatible_pair_during_care', claim_strategy: 'next_active_care_visit_at_or_after_ready' };

  it('separates current incubation rules from a completed report’s recorded policy without editing live pets', async () => {
    setupMetadata();
    server.use(http.get('*/api/rpg/progression-lab/', () => HttpResponse.json({ ...metadata, pet_incubation_policy: incubationPolicy })));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, {
      ...report, pet_incubation_policy: { ...incubationPolicy, duration_seconds: 7200 },
    });
    const livePets = spyHandler('post', /\/api\/pets\/.*/, {});
    server.use(simulation.handler, livePets.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByText('Reward and companion assumptions'));
    expect(within(screen.getByRole('region', { name: 'Current model incubation policy' })).getByText('24 hours')).toBeVisible();
    expect(simulation.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    const recorded = within(await screen.findByRole('region', { name: 'Recorded incubation policy' }));
    expect(recorded.getByText('2 hours')).toBeVisible();
    expect(recorded.queryByText('24 hours')).toBeNull();
    expect(simulation.calls).toHaveLength(1);
    expect(simulation.calls[0].body).toEqual(defaults);
    expect(livePets.calls).toHaveLength(0);
  });

  it('shows waiting and ready egg percentiles by day and distinguishes start, readiness and the hatch claim', async () => {
    setupMetadata();
    const incubationTrace = [
      { ...report.trace[0], incubating_eggs_p10: 0, incubating_eggs_p50: 1, incubating_eggs_p90: 1, ready_eggs_p10: 0, ready_eggs_p50: 0, ready_eggs_p90: 0 },
      { ...report.trace[0], day: 2, incubating_eggs_p10: 0, incubating_eggs_p50: 0, incubating_eggs_p90: 0, ready_eggs_p10: 0, ready_eggs_p50: 1, ready_eggs_p90: 1 },
      { ...report.trace[1], day: 8, incubating_eggs_p10: 0, incubating_eggs_p50: 0, incubating_eggs_p90: 0, ready_eggs_p10: 0, ready_eggs_p50: 0, ready_eggs_p90: 0 },
    ];
    const events = [
      { day: 1, source: 'incubation_started', target: 'Bat', duration_seconds: 86400, ready_day: 2 },
      { day: 2, source: 'incubation_ready', target: 'Bat' },
      { day: 8, source: 'hatch', target: 'Bat' },
    ];
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, {
      ...report, pet_incubation_policy: incubationPolicy, trace: incubationTrace, journey: { seed: 42, events, truncated: false },
    });
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    let table = await screen.findByRole('table', { name: 'Day 1 incubation state across simulated children' });
    expect(within(table).getByRole('row', { name: /Eggs incubating/ })).toHaveTextContent('0');
    expect(within(within(table).getByRole('row', { name: /Eggs incubating/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['0', '1', '1']);
    fireEvent.change(screen.getByRole('slider', { name: 'Inspect calendar day' }), { target: { value: '1' } });
    table = screen.getByRole('table', { name: 'Day 2 incubation state across simulated children' });
    expect(within(within(table).getByRole('row', { name: /Ready eggs awaiting hatch/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['0', '1', '1']);
    const state = screen.getByLabelText('Day 2 median state');
    expect(within(state).getByText('Hatched companions').nextElementSibling).toHaveTextContent('0');
    const journey = within(screen.getByRole('list', { name: 'Incubation journey events' }));
    expect(journey.getAllByRole('listitem')).toHaveLength(3);
    expect(journey.getByText('Incubation started')).toBeVisible();
    expect(journey.getByText('Egg ready')).toBeVisible();
    expect(journey.getByText('Hatch claimed')).toBeVisible();
    expect(journey.getByText(/Ready from Day 2/)).toBeVisible();
    expect(journey.getByText(/next active care visit/)).toBeVisible();
    await user.click(screen.getByText('Show event receipts'));
    expect(screen.getByText(/"incubation_started"/)).toBeVisible();
    expect(simulation.calls[0].body).toEqual(defaults);
  });

  it('leaves historical policy and egg counts unrecorded and labels a legacy hatch without inventing a wait', async () => {
    setupMetadata();
    server.use(http.get('*/api/rpg/progression-lab/', () => HttpResponse.json({ ...metadata, pet_incubation_policy: incubationPolicy })));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, {
      ...report, journey: { seed: 42, events: [{ day: 1, source: 'hatch', target: 'Bat' }], truncated: false },
    });
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    const recorded = within(await screen.findByRole('region', { name: 'Recorded incubation policy' }));
    expect(recorded.getByRole('status')).toHaveTextContent(/did not record an incubation policy/);
    expect(recorded.queryByText('24 hours')).toBeNull();
    const table = screen.getByRole('table', { name: 'Day 1 incubation state across simulated children' });
    expect(within(table).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(Array(6).fill('Unrecorded'));
    const journey = within(screen.getByRole('list', { name: 'Incubation journey events' }));
    expect(journey.getByText('Hatched companion')).toBeVisible();
    expect(journey.queryByText(/24 hours|Hatch claimed|Ready from/)).toBeNull();
  });

  it('compares per-child reward budgets while keeping the completed baseline and preserving exports', async () => {
    const rewardBudgetDefaults = { daily_coins: null };
    const current = { ...metadata, defaults: { ...defaults, reward_budget: rewardBudgetDefaults },
      reward_budget_defaults: rewardBudgetDefaults, reward_budget_limits: { daily_coins: { min: 0, max: 100000, nullable: true } } };
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/rpg/progression-lab/', () => HttpResponse.json(current)),
    );
    const stats = (value) => ({ p10: value, p50: value, p90: value, mean: value });
    const budgetResult = (daily_coins) => ({ daily_coins, summary: { raw_coins: stats(300), awarded_coins: stats(daily_coins === null ? 300 : 100), omitted_coins: stats(daily_coins === null ? 0 : 200), capped_days: stats(daily_coins === null ? 0 : 2) }, sources: [], assumptions: [] });
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...report, config: body, reward_budget: budgetResult(body.reward_budget.daily_coins) }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('region', { name: 'Reward budget forecast' });
    expect(simulation.calls[0].body.reward_budget).toEqual({ daily_coins: null });
    await user.click(screen.getByRole('button', { name: 'Keep as comparison' }));
    await user.click(screen.getByRole('button', { name: '50 Coins per child per day' }));
    expect(screen.getByText(/Inputs have changed/)).toBeVisible();
    expect(within(screen.getByRole('region', { name: 'Reward budget forecast' })).getByText('Uncapped per child')).toBeVisible();
    expect(simulation.calls).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Use light routine' }));
    expect(screen.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveValue(50);
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(2));
    expect(simulation.calls[1].body).toMatchObject({ active_days_per_week: 3, reward_budget: { daily_coins: 50 } });
    const forecast = within(screen.getByRole('region', { name: 'Reward budget forecast' }));
    expect(forecast.getByText('50 Coins per child per day')).toBeVisible();
    expect(forecast.getByText(/Comparison budget: Uncapped per child/)).toBeVisible();
    const table = within(forecast.getByRole('table', { name: 'Reward budget totals across simulated journeys' }));
    expect(table.getByRole('row', { name: /Coins awarded from budgeted sources/ })).toHaveTextContent('100');
    expect(table.getByRole('row', { name: /Coins awarded from budgeted sources/ })).toHaveTextContent('300');
    const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:budget-report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await user.click(screen.getByRole('button', { name: 'Download JSON report' }));
    const downloaded = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(JSON.parse(reader.result)); reader.readAsText(createUrl.mock.calls[0][0]); });
    expect(downloaded.config.reward_budget).toEqual({ daily_coins: 50 });
    await user.click(screen.getByText('Load a saved routine'));
    await user.upload(screen.getByLabelText('Saved routine'), new File([JSON.stringify(report)], 'old-report.json', { type: 'application/json' }));
    expect(await screen.findByText(/Saved routine loaded/)).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveValue(null);
    expect(screen.getByRole('button', { name: 'Uncapped' })).toHaveAttribute('aria-pressed', 'true');
    expect(simulation.calls).toHaveLength(2);
  });

  it('posts real purchasing assumptions, preserves the saved report while editing, and compares their economic assumptions', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/rpg/progression-lab/', () => HttpResponse.json({ ...sharedMetadata, defaults: sharedEconomyReport.config })),
    );
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...sharedEconomyReport, config: body }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('region', { name: 'Purchasing forecast' });
    expect(simulation.calls[0].body).toEqual(sharedEconomyReport.config);
    expect(within(screen.getByRole('region', { name: 'Recorded incubation policy' })).getByText('24 hours')).toBeVisible();
    const eggEvents = within(screen.getByRole('list', { name: 'Incubation journey events' }));
    expect(eggEvents.getByText('Incubation started')).toBeVisible();
    expect(eggEvents.getByText('Egg ready')).toBeVisible();
    expect(eggEvents.getByText('Hatch claimed')).toBeVisible();
    const totals = () => within(screen.getByRole('table', { name: 'Purchasing totals across simulated journeys' }));
    const cost = formatCurrency(sharedEconomyReport.economy.summary.family_cost_cents.p50 / 100);
    expect(totals().getByRole('row', { name: /Estimated reward and print fulfillment cost/ })).toHaveTextContent(cost);
    await user.click(screen.getByRole('button', { name: 'Keep as comparison' }));
    const familyCost = within(screen.getByRole('group', { name: 'Reward 1' })).getByRole('spinbutton', { name: 'Family cost per purchase ($)' });
    await user.clear(familyCost);
    await user.type(familyCost, '7.25');
    expect(screen.getByText(/Inputs have changed/)).toBeVisible();
    expect(totals().getByRole('row', { name: /Estimated reward and print fulfillment cost/ })).toHaveTextContent(cost);
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(2));
    expect(simulation.calls[1].body.economy.offers[0].family_cost_cents).toBe(725);
    expect(await screen.findByText(/Purchasing assumptions differ/)).toBeVisible();
    expect(totals().getByRole('columnheader', { name: 'Comparison median' })).toBeVisible();
    const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:economy-report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await user.click(screen.getByRole('button', { name: 'Download JSON report' }));
    const downloaded = await new Promise((resolve) => { const reader = new FileReader(); reader.onload = () => resolve(JSON.parse(reader.result)); reader.readAsText(createUrl.mock.calls[0][0]); });
    expect(downloaded.config.economy.offers[0].family_cost_cents).toBe(725);
  });

  it('uses the explicit purchasing example, preserves it through routine presets, and imports old routines with purchasing off', async () => {
    const current = { ...metadata, ...economyMetadata, defaults: { ...defaults, economy: economyDefaults } };
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/rpg/progression-lab/', () => HttpResponse.json(current)),
    );
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...report, config: body }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Load purchasing example (90 days, 10 children)' }));
    expect(screen.getByRole('spinbutton', { name: 'Simulated children' })).toHaveValue(10);
    expect(screen.getByRole('checkbox', { name: 'Model purchases and family costs' })).toBeChecked();
    expect(simulation.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Use light routine' }));
    expect(screen.getByRole('textbox', { name: 'Reward name' })).toHaveValue('Example outing');
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(1));
    expect(simulation.calls[0].body).toMatchObject({ active_days_per_week: 3, economy: { enabled: true, offers: [{ key: 'example-outing', family_cost_cents: 500 }] } });
    await user.click(screen.getByText('Load a saved routine'));
    await user.upload(screen.getByLabelText('Saved routine'), new File([JSON.stringify(report)], 'old-report.json', { type: 'application/json' }));
    expect(await screen.findByText(/Saved routine loaded/)).toBeVisible();
    expect(screen.getByRole('checkbox', { name: 'Model purchases and family costs' })).not.toBeChecked();
    expect(simulation.calls).toHaveLength(1);
  });

  it('renders the real endpoint contract with explicit subset totals, inventory, level and receipt metadata', async () => {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())),
      http.get('*/api/rpg/progression-lab/', () => HttpResponse.json({ ...sharedMetadata, defaults: sharedReport.config })),
    );
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, sharedReport);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('region', { name: 'Simulation report' });
    expect(simulation.calls[0].body).toEqual(sharedReport.config);
    expect(screen.getByText('Character level')).toBeInTheDocument();
    expect(screen.getByText('Inventory units held')).toBeInTheDocument();
    expect(screen.getByText('Finite targets in this scenario')).toBeInTheDocument();
    expect(screen.getByText(/not total app exhaustion/)).toBeInTheDocument();
    expect(within(screen.getByRole('table', { name: 'Milestone completion and calendar days among successful journeys' })).getAllByRole('row')).toHaveLength(sharedReport.milestones.length + 1);
    await user.click(screen.getByText('Show exact scenario and model summary'));
    expect(screen.getByText(sharedReport.rules_fingerprint, { exact: false })).toBeVisible();
  });

  it('uses server defaults and limits, without running or loading household records', async () => {
    setupMetadata();
    const households = vi.fn();
    server.use(http.get('*/api/children/', () => { households(); return HttpResponse.json([]); }));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, report);
    server.use(simulation.handler);
    renderWithProviders(<ProgressionLab />);
    expect(await screen.findByRole('form', { name: 'Progression scenario' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'Simulated children' })).toHaveAttribute('max', '40');
    expect(screen.getByRole('spinbutton', { name: 'Reading minutes per active day' })).toHaveValue(10);
    await waitFor(() => expect(screen.getByText('Private household shops')).toBeVisible());
    expect(simulation.calls).toHaveLength(0);
    expect(households).not.toHaveBeenCalled();
  });

  it('submits the exact bounded anonymous scenario and shows ranges without inventing missing milestone dates', async () => {
    setupMetadata();
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, report);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(1));
    expect(simulation.calls[0].url).toMatch(/\/api\/rpg\/progression-lab\/simulate\/$/);
    expect(simulation.calls[0].body).toEqual(defaults);
    const table = await screen.findByRole('table', { name: 'Milestone completion and calendar days among successful journeys' });
    const first = within(table).getByRole('row', { name: /First companion/ });
    expect(first).toHaveTextContent('50%');
    expect(first).toHaveTextContent('10 / 20 children');
    expect(first).toHaveTextContent('Day 14');
    const missing = within(table).getByRole('row', { name: /Every companion/ });
    expect(within(missing).getAllByText('Not reached')).toHaveLength(3);
    expect(missing).not.toHaveTextContent('Day 0');
    fireEvent.change(screen.getByRole('slider', { name: 'Inspect calendar day' }), { target: { value: '1' } });
    expect(screen.getByText('900')).toBeVisible();
    expect(screen.getByText(/Household shops, real-world rewards and purchasing decisions are excluded/)).toBeVisible();
    expect(within(screen.getByRole('table', { name: 'Sources: mean totals per simulated child' })).getByRole('row', { name: /reading/ })).toHaveTextContent('100');
  });

  it('compares completed scenarios and marks edited inputs until another result succeeds', async () => {
    setupMetadata();
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({
      ...report, config: body,
      milestones: report.milestones.map((entry) => entry.key === 'first_pet' ? { ...entry, p50_days: body.reading_minutes === 30 ? 9 : 14 } : entry),
    }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await user.click(await screen.findByRole('button', { name: 'Keep as comparison' }));
    const reading = screen.getByRole('spinbutton', { name: 'Reading minutes per active day' });
    await user.clear(reading);
    await user.type(reading, '30');
    expect(screen.getByText(/Inputs have changed/)).toBeVisible();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Forecast horizon' }), '30');
    await user.click(screen.getByRole('checkbox', { name: 'One journal entry per active day' }));
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(2));
    expect(simulation.calls[1].body).toEqual({ ...defaults, reading_minutes: 30, horizon_days: 30, journal_per_day: false });
    await waitFor(() => expect(screen.queryByText(/Inputs have changed/)).toBeNull());
    expect(screen.getByRole('columnheader', { name: 'Comparison median' })).toBeVisible();
    expect(screen.getByText(/Comparison versions: unavailable or different/)).toBeVisible();
    expect(screen.getByRole('row', { name: /First companion/ })).toHaveTextContent('Day 9');
    expect(screen.getByRole('row', { name: /First companion/ })).toHaveTextContent('Day 14');
    await user.click(screen.getByRole('button', { name: 'Clear comparison' }));
    expect(screen.queryByRole('columnheader', { name: 'Comparison median' })).toBeNull();
  });

  it.each(['rules', 'catalog', 'engine'])('warns when the %s version changes between compared forecasts', async (kind) => {
    setupMetadata();
    const first = { ...report, rules_fingerprint: 'a'.repeat(64), catalog: { ...report.catalog, fingerprint: 'b'.repeat(64) }, engine_version: 'version-1' };
    const next = {
      ...first,
      ...(kind === 'rules' ? { rules_fingerprint: 'c'.repeat(64) } : {}),
      ...(kind === 'catalog' ? { catalog: { ...first.catalog, fingerprint: 'c'.repeat(64) } } : {}),
      ...(kind === 'engine' ? { engine_version: 'version-2' } : {}),
    };
    let runs = 0;
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, () => ++runs === 1 ? first : next);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await user.click(await screen.findByRole('button', { name: 'Keep as comparison' }));
    expect(screen.queryByText(/Comparison versions: unavailable or different/)).toBeNull();
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    expect(await screen.findByText(/Comparison versions: unavailable or different/)).toBeVisible();
    expect(simulation.calls).toHaveLength(2);
  });

  it('identifies expired unfinished challenges without presenting uncompleted targets as available runway', async () => {
    setupMetadata();
    const expired = { ...report, summary: { ...report.summary, expired_oneoff_challenges_p50: 1 } };
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, expired);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    expect(await screen.findByText(/Those missed targets remain uncompleted and do not provide future runway/)).toBeVisible();
    expect(screen.getByText('Expired unfinished one-time challenges (median)')).toBeVisible();
    expect(screen.getByRole('img', { name: 'Median modeled targets not completed over calendar days' })).toBeVisible();
  });

  it('retains inputs and the previous report on a failed run and exposes server field errors', async () => {
    setupMetadata();
    let failure = false;
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, () => failure
      ? HttpResponse.json({ reading_minutes: ['Use fewer reading minutes.'] }, { status: 400 }) : report);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('region', { name: 'Simulation report' });
    failure = true;
    const reading = screen.getByRole('spinbutton', { name: 'Reading minutes per active day' });
    await user.clear(reading);
    await user.type(reading, '25');
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    expect(await screen.findByText('Use fewer reading minutes.')).toBeVisible();
    expect(reading).toHaveValue(25);
    expect(reading).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('region', { name: 'Simulation report' })).toBeVisible();
    expect(simulation.calls).toHaveLength(2);
  });

  it('loads only an exported routine locally and requires a fresh explicit simulation', async () => {
    setupMetadata();
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ body }) => ({ ...report, config: body }));
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await screen.findByRole('region', { name: 'Simulation report' });
    await user.click(screen.getByText('Load a saved routine'));
    const config = { ...defaults, reading_minutes: 25, seed: 17 };
    const file = new File([JSON.stringify({ ...report, config, summary: { coins_p50: 99999999 } })], 'saved-report.json', { type: 'application/json' });
    await user.upload(screen.getByLabelText('Saved routine'), file);
    expect(await screen.findByText(/Saved routine loaded/)).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Reading minutes per active day' })).toHaveValue(25);
    expect(screen.getByRole('spinbutton', { name: 'Random seed' })).toHaveValue(17);
    expect(screen.getByText(/Inputs have changed/)).toBeVisible();
    expect(screen.queryByText('99,999,999')).toBeNull();
    expect(simulation.calls).toHaveLength(1);
    await user.click(screen.getByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(simulation.calls).toHaveLength(2));
    expect(simulation.calls[1].body).toEqual(config);
  });

  it.each([
    ['invalid JSON', 'not json'],
    ['unknown targeting fields', JSON.stringify({ schema_version: 1, config: { ...defaults, user_id: 1 } })],
    ['out-of-range values', JSON.stringify({ schema_version: 1, config: { ...defaults, trials: 41 } })],
    ['wrong value types', JSON.stringify({ schema_version: 1, config: { ...defaults, seed: '42' } })],
    ['missing fields', JSON.stringify({ schema_version: 1, config: { seed: 42 } })],
    ['oversized files', ' '.repeat(1_000_001)],
  ])('rejects %s in saved reports without changing the routine or running', async (_label, contents) => {
    setupMetadata();
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, report);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByText('Load a saved routine'));
    await user.upload(screen.getByLabelText('Saved routine'), new File([contents], 'invalid.json', { type: 'application/json' }));
    expect(await screen.findByText(/Your current inputs have been kept/)).toBeVisible();
    expect(screen.getByRole('spinbutton', { name: 'Random seed' })).toHaveValue(defaults.seed);
    expect(screen.getByRole('spinbutton', { name: 'Simulated children' })).toHaveValue(defaults.trials);
    expect(simulation.calls).toHaveLength(0);
  });

  it('offers retry for failed metadata reads and downloads the exact successful report', async () => {
    setupMetadata();
    let reads = 0;
    server.use(http.get('*/api/rpg/progression-lab/', () => ++reads === 1
      ? HttpResponse.json({ detail: 'Unavailable' }, { status: 503 }) : HttpResponse.json(metadata)));
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, report);
    server.use(simulation.handler);
    const { user } = renderWithProviders(<ProgressionLab />);
    await user.click(await screen.findByRole('button', { name: 'Try again' }));
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    const createUrl = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:progression-report');
    const revokeUrl = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    await user.click(await screen.findByRole('button', { name: 'Download JSON report' }));
    expect(createUrl).toHaveBeenCalledWith(expect.any(Blob));
    expect(click).toHaveBeenCalledOnce();
    expect(revokeUrl).toHaveBeenCalledWith('blob:progression-report');
    expect(reads).toBe(2);
  });

  it('does not request designer data for children, and does not show controls after a forbidden staff probe', async () => {
    const reads = vi.fn();
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/rpg/progression-lab/', () => { reads(); return new HttpResponse(null, { status: 403 }); }),
    );
    const child = renderWithProviders(<ProgressionLab />);
    await screen.findByText('Progression lab is available to staff parents.');
    expect(reads).not.toHaveBeenCalled();
    child.unmount();
    server.use(http.get('*/api/auth/me/', () => HttpResponse.json(buildParent())));
    renderWithProviders(<ProgressionLab />);
    await screen.findByText('Progression lab is available to staff parents.');
    expect(reads).toHaveBeenCalledOnce();
    expect(screen.queryByRole('form', { name: 'Progression scenario' })).toBeNull();
  });

  it('fences delayed simulation results when the account is replaced', async () => {
    setupMetadata();
    let finish;
    server.use(http.post('*/api/rpg/progression-lab/simulate/', async () => {
      await new Promise((resolve) => { finish = resolve; });
      return HttpResponse.json({ ...report, milestones: [{ ...report.milestones[0], label: 'Previous account milestone' }] });
    }));
    const { user } = renderWithProviders(<SwitchAccount />);
    await user.click(await screen.findByRole('button', { name: 'Run simulation' }));
    await waitFor(() => expect(finish).toBeDefined());
    expect(screen.getByRole('button', { name: 'Running simulation…' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Switch account' }));
    await screen.findByRole('button', { name: 'Run simulation' });
    await act(async () => { finish(); });
    expect(screen.queryByText('Previous account milestone')).toBeNull();
    expect(screen.queryByRole('region', { name: 'Simulation report' })).toBeNull();
  });
});

function SwitchAccount() {
  const { setUser } = useAuth();
  return <><button onClick={() => {
    localStorage.setItem('abby_auth_token', 'replacement-test-session');
    setUser(buildParent({ id: 101, family: { id: 2 } }));
  }}>Switch account</button><ProgressionLab /></>;
}

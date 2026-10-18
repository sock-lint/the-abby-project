import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import metadata from '../../../contracts/api/fixtures/progression-lab-metadata.json';
import report from '../../../contracts/api/fixtures/progression-lab-report.json';
import economyReport from '../../../contracts/api/fixtures/progression-lab-economy-report.json';
import budgetReport from '../../../contracts/api/fixtures/progression-lab-reward-budget-report.json';
import commitmentReport from '../../../contracts/api/fixtures/progression-lab-commitment-report.json';
import expeditionBudgetReport from '../../../contracts/api/fixtures/progression-lab-expedition-budget-report.json';
import experiments from '../../../contracts/api/fixtures/progression-experiment-list.json';
import comparison from '../../../contracts/api/fixtures/progression-experiment-comparison.json';
import commitmentComparison from '../../../contracts/api/fixtures/progression-experiment-commitment-comparison.json';
import expeditionBudgetComparison from '../../../contracts/api/fixtures/progression-experiment-expedition-budget-comparison.json';
import decided from '../../../contracts/api/fixtures/progression-experiment-decided.json';
import observations from '../../../contracts/api/fixtures/progression-observations-empty.json';
import observed from '../../../contracts/api/fixtures/progression-experiment-observed.json';
import { listProgressionExperiments, createProgressionExperiment, getProgressionExperiment, updateProgressionExperiment, compareProgressionExperiment, getProgressionComparison, recordProgressionDecision, getProgressionObservations, saveProgressionObservation } from './progressionExperiments';
import { getProgressionLab, simulateProgressionLab } from './index';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';

describe('Progression lab shared API fixtures', () => {
  it('transports server-owned experiment evidence and decisions without accepting client reports', async () => {
    const root = '/api/rpg/progression-lab/experiments/';
    const id = decided.id;
    server.use(
      http.get(`*${root}`, () => HttpResponse.json(experiments)),
      http.get(`*${root}${id}/`, () => HttpResponse.json(decided)),
      http.get(`*${root}${id}/comparisons/${comparison.id}/`, () => HttpResponse.json(comparison)),
      http.get('*/api/rpg/progression-lab/observations/', () => HttpResponse.json(observations)),
    );
    expect(await listProgressionExperiments()).toEqual(experiments);
    expect(await getProgressionExperiment(id)).toEqual(decided);
    expect(await getProgressionComparison(id, comparison.id)).toEqual(comparison);
    expect(await getProgressionObservations()).toEqual(observations);
    const create = spyHandler('post', new RegExp(`${root}$`), decided);
    const save = spyHandler('patch', new RegExp(`${root}${id}/$`), decided);
    const compare = spyHandler('post', new RegExp(`${root}${id}/compare/$`), comparison);
    const decide = spyHandler('post', new RegExp(`${root}${id}/decisions/$`), decided);
    server.use(create.handler, save.handler, compare.handler, decide.handler);
    const input = comparison.inputs;
    expect(await createProgressionExperiment(input)).toEqual(decided);
    expect(create.calls[0].body).toEqual(input);
    await updateProgressionExperiment(id, { revision: 1, ...input });
    expect(save.calls[0].body).toEqual({ revision: 1, ...input });
    expect(await compareProgressionExperiment(id, { revision: 1 })).toEqual(comparison);
    expect(compare.calls[0].body).toEqual({ revision: 1 });
    const decision = decided.decisions[0];
    const payload = { revision: 1, comparison_id: comparison.id, outcome: decision.outcome, rationale: decision.rationale, next_action: decision.next_action, review_on: decision.review_on };
    expect(await recordProgressionDecision(id, payload)).toEqual(decided);
    expect(decide.calls[0].body).toEqual(payload);
    expect(comparison.control.config.reward_budget.daily_coins).toBeNull();
    expect(comparison.candidate.config.reward_budget.daily_coins).toBe(100);
    expect(comparison.binding.catalog_fingerprint).toBe(comparison.control.catalog.fingerprint);
    expect(comparison.inputs.candidate_policy).toBe('envelope');
    expect(comparison.candidate.config.reward_commitment.enabled).toBe(false);
    expect(comparison.evaluation.proposal.evaluated_by_current_engine).toBe(true);
    expect(comparison.evaluation.proposal.live_ready).toBe(false);
    expect(observations.policy.is_live_experiment).toBe(false);
    expect(observations.status).toBe('insufficient_evidence');
    const capture = spyHandler('post', new RegExp(`${root}${id}/observations/$`), observed);
    server.use(capture.handler);
    expect(await saveProgressionObservation(id, { revision: 1 })).toEqual(observed);
    expect(capture.calls[0].body).toEqual({ revision: 1 });
    expect(observed.observations[0].payload).toEqual(observations);
  });

  it('reads the server rules, bounds and anonymous initial state through the authenticated client', async () => {
    const requests = [];
    server.use(http.get('*/api/rpg/progression-lab/', ({ request }) => {
      const url = new URL(request.url);
      requests.push({ path: url.pathname, auth: request.headers.get('Authorization'), queryKeys: [...url.searchParams.keys()] });
      expect(url.searchParams.get('_abby_session')).toBeTruthy();
      return HttpResponse.json(metadata);
    }));
    const response = await getProgressionLab();
    expect(response).toEqual(metadata);
    expect(requests).toEqual([{ path: '/api/rpg/progression-lab/', auth: 'Token test-session', queryKeys: ['_abby_session'] }]);
    expect(response.coverage.initial_state).toEqual({ coins: 0, xp: 0, pets: 0, mounts: 0, inventory: 0 });
    expect(response.limits.horizon_days.choices).toContain(report.config.horizon_days);
    expect(response.catalog.fingerprint).toMatch(/^[a-f0-9]{64}$/);
  });

  it('transports the separate full-promise prototype and its saved server comparison', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, commitmentReport);
    const root = '/api/rpg/progression-lab/experiments/';
    const create = spyHandler('post', new RegExp(`${root}$`), { id: 'commitment-fixture', ...commitmentComparison.inputs });
    const compare = spyHandler('post', new RegExp(`${root}commitment-fixture/compare/$`), commitmentComparison);
    server.use(simulation.handler, create.handler, compare.handler);
    const response = await simulateProgressionLab(commitmentReport.config);
    expect(simulation.calls[0].body.reward_commitment).toEqual({ enabled: true });
    expect(response.config.reward_budget.daily_coins).toBeNull();
    expect(response.reward_commitment).toEqual(commitmentReport.reward_commitment);
    expect(response.reward_commitment.policy.daily_coins).toBe(100);
    expect(response.reward_commitment.policy.expedition_daily_coins).toBe(75);
    expect(response.reward_commitment.policy.activity_pouch_daily_coins).toBe(25);
    for (const day of response.trace) {
      expect(day.reward_commitment_expedition_today_p90).toBeLessThanOrEqual(75);
      expect(day.reward_commitment_activity_pouch_today_p90).toBeLessThanOrEqual(25);
    }
    await createProgressionExperiment(commitmentComparison.inputs);
    expect(create.calls[0].body.candidate_policy).toBe('commitment100');
    const saved = await compareProgressionExperiment('commitment-fixture', { revision: 1 });
    expect(compare.calls[0].body).toEqual({ revision: 1 });
    expect(saved.inputs.candidate_policy).toBe('commitment100');
    expect(saved.control.config.reward_commitment.enabled).toBe(false);
    expect(saved.candidate.config.reward_commitment.enabled).toBe(true);
    expect(saved.candidate.config.reward_budget.daily_coins).toBeNull();
    expect(saved.candidate).toEqual(commitmentReport);
    expect(saved.candidate.reward_commitment.summary.activity_pouch_committed.p50).toBeGreaterThan(0);
    expect(saved.candidate.rules_fingerprint).toBe(metadata.rules_fingerprint);
    expect(saved.evaluation.proposal.live_ready).toBe(false);
  });

  it('posts only the anonymous scenario and preserves completion denominators, missing dates and subset totals', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, ({ request }) => {
      expect(request.headers.get('Authorization')).toBe('Token test-session');
      return report;
    });
    server.use(simulation.handler);
    const response = await simulateProgressionLab(report.config);
    expect(response).toEqual(report);
    expect(simulation.calls).toHaveLength(1);
    expect(simulation.calls[0].url).toMatch(/\/api\/rpg\/progression-lab\/simulate\/$/);
    expect(simulation.calls[0].body).toEqual(report.config);
    expect(response.trace).toHaveLength(report.config.horizon_days);
    const unreached = response.milestones.find((milestone) => milestone.completion_rate === 0);
    expect(unreached).toMatchObject({ completed_trials: 0, trials: report.config.trials, p10_days: null, p50_days: null, p90_days: null });
    for (const milestone of response.milestones) expect(milestone.completion_rate).toBe(milestone.completed_trials / milestone.trials);
    expect(response.summary.finite_content_total).toBe(Object.values(response.summary.finite_breakdown).reduce((sum, count) => sum + count, 0));
    expect(response.summary.finite_completed_p50 + response.summary.finite_remaining_p50).toBe(response.summary.finite_content_total);
    expect(response.journey.seed).toBe(report.config.seed);
    expect(response.rules_fingerprint).toBe(metadata.rules_fingerprint);
  });

  it('transports shared launch and item quotas while retaining their accounting and unchanged Coin hypothesis', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, expeditionBudgetReport);
    const root = '/api/rpg/progression-lab/experiments/';
    const create = spyHandler('post', new RegExp(`${root}$`), { id: 'quota-fixture', ...expeditionBudgetComparison.inputs });
    const compare = spyHandler('post', new RegExp(`${root}quota-fixture/compare/$`), expeditionBudgetComparison);
    server.use(simulation.handler, create.handler, compare.handler);
    const response = await simulateProgressionLab(expeditionBudgetReport.config);
    expect(simulation.calls[0].body.expedition_budget).toEqual({ daily_launches: 1, daily_items: 1 });
    expect(response.reward_commitment.enabled).toBe(true);
    for (const day of response.trace) {
      expect(day.expedition_budget_launches_today_p90).toBeLessThanOrEqual(1);
      expect(day.expedition_budget_items_today_p90).toBeLessThanOrEqual(1);
    }
    const totals = response.expedition_budget.summary;
    expect(totals.requested_trips.mean).toBeCloseTo(totals.eligible_trips.mean + totals.unavailable_mount_trips.mean, 0);
    expect(totals.eligible_trips.mean).toBeCloseTo(totals.launched_trips.mean + totals.prevented_trips.mean, 0);
    expect(totals.slots_requested.mean).toBeCloseTo(totals.slots_promised.mean + totals.slots_withheld_by_budget.mean + totals.slots_unfilled_by_pool.mean, 0);
    expect(totals.slots_promised.mean).toBeCloseTo(totals.claimed_items.mean - totals.grandfathered_claimed_items.mean + totals.pending_items.mean - totals.grandfathered_pending_items.mean, 0);
    const input = expeditionBudgetComparison.inputs;
    await createProgressionExperiment(input);
    expect(create.calls[0].body).toEqual(input);
    expect(input.candidate_daily_coins).toBeNull();
    expect(input.candidate_policy).toBe('expedition_limits');
    const saved = await compareProgressionExperiment('quota-fixture', { revision: 1 });
    expect(compare.calls[0].body).toEqual({ revision: 1 });
    expect(saved.control.config.expedition_budget).toEqual({ daily_launches: null, daily_items: null });
    expect(saved.control.config.reward_commitment).toEqual(saved.candidate.config.reward_commitment);
    expect(saved.control.config.reward_budget).toEqual(saved.candidate.config.reward_budget);
    expect(saved.candidate).toEqual(expeditionBudgetReport);
    expect(saved.candidate.rules_fingerprint).toBe(metadata.rules_fingerprint);
    for (const check of saved.evaluation.checks) expect(check.candidate.trials).toBe(input.config.trials);
  });

  it('preserves purchase timing, calendar budgets and separate Coin and money flows', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, economyReport);
    server.use(simulation.handler);
    const response = await simulateProgressionLab(economyReport.config);
    expect(simulation.calls).toHaveLength(1);
    expect(simulation.calls[0].url).toMatch(/\/api\/rpg\/progression-lab\/simulate\/$/);
    expect(simulation.calls[0].body).toEqual(economyReport.config);
    expect(response.economy.enabled).toBe(true);
    expect(response.economy.exchange_rate_coins_per_dollar).toBe(10);
    expect(response.economy.offers.find((offer) => offer.kind === 'printing').coin_price).toBe(3);
    expect(response.economy.months.map((month) => month.month)).toEqual(['2026-01', '2026-02']);
    for (const month of response.economy.months) {
      expect(month.family_cost_cents.p90).toBeLessThanOrEqual(600);
      expect(month.print_minutes.p90).toBeLessThanOrEqual(30);
      expect(month.print_grams.p90).toBeLessThanOrEqual(20);
    }
    const totals = response.economy.summary;
    expect(totals.coin_balance.mean).toBeCloseTo(totals.coins_earned.mean + totals.coins_exchanged.mean - totals.coins_spent.mean, 1);
    expect(totals.money_remaining_cents.mean).toBeCloseTo(totals.money_earned_cents.mean - totals.money_exchanged_cents.mean, 1);
    expect(totals.parent_liability_cents.mean).toBeCloseTo(totals.money_remaining_cents.mean + totals.family_cost_cents.mean, 1);
    for (const offer of response.economy.offers) {
      expect(offer.first_purchase.trials).toBe(economyReport.config.trials);
      expect(offer.first_coin_affordable.trials).toBe(economyReport.config.trials);
    }
  });

  it('propagates a rejected scenario without silently retrying the request', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/,
      HttpResponse.json({ detail: 'Invalid Progression Lab value for trials.' }, { status: 400 }));
    server.use(simulation.handler);
    await expect(simulateProgressionLab({ ...report.config, trials: 41 })).rejects.toMatchObject({ status: 400 });
    expect(simulation.calls).toHaveLength(1);
  });

  it('keeps the daily per-child automatic Coin budget and its source accounting through transport', async () => {
    const simulation = spyHandler('post', /\/api\/rpg\/progression-lab\/simulate\/$/, budgetReport);
    server.use(simulation.handler);
    const response = await simulateProgressionLab(budgetReport.config);
    expect(simulation.calls[0].body.reward_budget).toEqual({ daily_coins: 5 });
    expect(response.reward_budget.daily_coins).toBe(5);
    const { summary, sources } = response.reward_budget;
    expect(summary.omitted_coins.p50).toBeGreaterThan(0);
    expect(summary.raw_coins.mean).toBeCloseTo(summary.awarded_coins.mean + summary.omitted_coins.mean, 1);
    expect(sources.map((source) => source.source)).toEqual(expect.arrayContaining(['expeditions', 'expeditions_salvage', 'coin_pouches']));
    expect(response.trace.at(-1).reward_budget_awarded_coins_p90).toBeLessThanOrEqual(response.summary.active_days * 5);
    expect(response.config.chore_coins).toBe(5);
    expect(response.rules_fingerprint).toBe(metadata.rules_fingerprint);
  });
});

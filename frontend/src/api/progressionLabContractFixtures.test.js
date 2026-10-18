import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import metadata from '../../../contracts/api/fixtures/progression-lab-metadata.json';
import report from '../../../contracts/api/fixtures/progression-lab-report.json';
import economyReport from '../../../contracts/api/fixtures/progression-lab-economy-report.json';
import budgetReport from '../../../contracts/api/fixtures/progression-lab-reward-budget-report.json';
import { getProgressionLab, simulateProgressionLab } from './index';
import { server } from '../test/server';
import { spyHandler } from '../test/spy';

describe('Progression lab shared API fixtures', () => {
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

import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import ProgressionRewardBudgetReport from './ProgressionRewardBudgetReport';

const stats = (value) => ({ p10: value - 1, p50: value, p90: value + 1, mean: value + 0.5 });
const budget = { daily_coins: 100, summary: { raw_coins: stats(400), awarded_coins: stats(200), omitted_coins: stats(200), capped_days: stats(2) },
  sources: [{ source: 'expeditions', raw_coins: stats(300), awarded_coins: stats(180), omitted_coins: stats(120) }, { source: 'expeditions_salvage', raw_coins: stats(20), awarded_coins: stats(10), omitted_coins: stats(10) }, { source: 'coin_pouches', raw_coins: stats(80), awarded_coins: stats(10), omitted_coins: stats(70) }],
  assumptions: ['Unused daily allowance does not carry over.'],
};

describe('Reward budget forecast', () => {
  it('shows complete ranges, separate source accounting and the immutable comparison budget', async () => {
    const { user } = renderWithProviders(<ProgressionRewardBudgetReport budget={budget} baseline={{ ...budget, daily_coins: null, summary: { ...budget.summary, awarded_coins: stats(400) } }} />, { withAuth: false });
    const totals = within(screen.getByRole('table', { name: 'Reward budget totals across simulated journeys' }));
    const awarded = totals.getByRole('row', { name: /Coins awarded from budgeted sources/ });
    expect(awarded).toHaveTextContent('199');
    expect(awarded).toHaveTextContent('200');
    expect(awarded).toHaveTextContent('201');
    expect(awarded).toHaveTextContent('200.5');
    expect(awarded).toHaveTextContent('400');
    expect(screen.getByText('100 Coins per child per day')).toBeVisible();
    expect(screen.getByText(/Comparison budget: Uncapped per child/)).toBeVisible();
    const sources = within(screen.getByRole('table', { name: 'Reward budget source totals, mean per simulated child' }));
    expect(sources.getByRole('row', { name: /Direct expedition Coins/ })).toHaveTextContent('180.5');
    expect(sources.getByRole('row', { name: /Expedition duplicate salvage/ })).toHaveTextContent('10.5');
    expect(sources.getByRole('row', { name: /All Coin pouches/ })).toHaveTextContent('70.5');
    expect(screen.getByText(/They are not the total from a separate uncapped journey/)).toBeVisible();
    await user.click(screen.getByText('Reward budget model assumptions'));
    expect(screen.getByText('Unused daily allowance does not carry over.')).toBeVisible();
  });

  it('keeps older missing budget reports absent and distinguishes zero from uncapped', () => {
    const first = renderWithProviders(<ProgressionRewardBudgetReport />, { withAuth: false });
    expect(screen.queryByRole('region', { name: 'Reward budget forecast' })).toBeNull();
    first.unmount();
    renderWithProviders(<ProgressionRewardBudgetReport budget={{ ...budget, daily_coins: 0 }} />, { withAuth: false });
    expect(screen.getByText('0 Coins per child per day')).toBeVisible();
    expect(screen.queryByRole('columnheader', { name: 'Comparison median' })).toBeNull();
  });
});

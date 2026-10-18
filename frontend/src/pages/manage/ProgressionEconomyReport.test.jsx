import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import ProgressionEconomyReport from './ProgressionEconomyReport';
import { economyDefaults, economyResult } from './progressionEconomyTestData';

describe('Purchasing forecast', () => {
  it('separates Coins, earned money and estimated family cost without multiplying alternate trials', () => {
    renderWithProviders(<ProgressionEconomyReport economy={economyResult} config={economyDefaults} />, { withAuth: false });
    const totals = within(screen.getByRole('table', { name: 'Purchasing totals across simulated journeys' }));
    expect(totals.getByRole('row', { name: /Coins earned from activities/ })).toHaveTextContent('100');
    expect(totals.getByRole('row', { name: /Earned money exchanged for Coins/ })).toHaveTextContent('$1.00');
    expect(totals.getByRole('row', { name: /Earned money still owed to the child/ })).toHaveTextContent('$4.00');
    expect(totals.getByRole('row', { name: /Fulfillment cost plus money still owed/ })).toHaveTextContent('$6.50');
    expect(screen.getByText(/Separate medians can come from different journeys/)).toBeVisible();
    expect(screen.getByText(/Coins remain a separate currency with no cash-out value/)).toBeVisible();
    const reward = within(screen.getByRole('table', { name: 'Affordability and actual purchases for each reward' })).getByRole('row', { name: /Example outing/ });
    expect(reward).toHaveTextContent('66.67% (2/3)');
    expect(reward).toHaveTextContent('33.33% (1/3)');
    const month = within(screen.getByRole('table', { name: 'Calendar month purchasing results, median per child' })).getByRole('row', { name: /2026-01/ });
    expect(month).toHaveTextContent('Days 1–30');
    expect(month).toHaveTextContent('$2.50');
  });

  it('distinguishes a disabled comparison from a measured zero and keeps missing milestones unavailable', () => {
    const result = { ...economyResult, offers: [{ ...economyResult.offers[0], first_purchase: { completion_rate: 0, completed_trials: 0, trials: 3, p10_days: null, p50_days: null, p90_days: null } }] };
    renderWithProviders(<ProgressionEconomyReport economy={result} baseline={{ enabled: false }} config={economyDefaults} />, { withAuth: false });
    expect(screen.getByRole('columnheader', { name: 'Comparison median' })).toBeVisible();
    expect(screen.getAllByText('Purchasing was off')).toHaveLength(16);
    expect(screen.getByText('Not reached')).toBeVisible();
    expect(screen.queryByText(/Median day 0/)).toBeNull();
  });

  it('does not invent a spending forecast for a disabled report', () => {
    renderWithProviders(<ProgressionEconomyReport economy={{ enabled: false }} config={economyDefaults} />, { withAuth: false });
    expect(screen.queryByRole('region', { name: 'Purchasing forecast' })).toBeNull();
  });
});

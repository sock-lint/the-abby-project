import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { ProgressionObservations } from './ProgressionExperimentEvidence';
import empty from '../../../../contracts/api/fixtures/progression-observations-empty.json';
import earned from '../../../../contracts/api/fixtures/progression-observations-earned.json';

const evidence = {
  ...empty,
  status: 'observations_available',
  cohort: { ...empty.cohort, scope: 'active_family_children', registered_within_days: null, eligible_children: 2 },
  activity: { ledger_active_children: 2, ledger_active_child_days: 12, meaningful_active_children: 2, meaningful_active_child_days: 6 },
  earning_sources: [
    { key: 'reading', label: 'Reading', coins: 30, entries: 6, kind: 'recurring' },
    { key: 'birthday', label: 'Birthdays', coins: 200, entries: 1, kind: 'occasional' },
    { key: 'unattributed', label: 'Unattributed credits', coins: 40, entries: 1, kind: 'unattributed' },
  ],
  earning_pace: { status: 'available', recurring_coins: 30, active_child_days: 6, coins_per_active_day: 5, excluded_credits: 240, attribution_complete: false, provisional: true },
  shop_rewards: [
    { reward_id: 1, name: 'Practice outing', cost_coins: 51, stock: null, days_to_earn: 11 },
    { reward_id: 2, name: 'Movie night', cost_coins: 100, stock: 0, days_to_earn: 20 },
  ],
};

describe('Observed family Coin economy', () => {
  it('renders real Django earning and shop evidence without recalculating prices', () => {
    renderWithProviders(<ProgressionObservations observations={earned} />);
    expect(screen.getByText(/12.5 Coins per active child-day/)).toBeVisible();
    const shop = screen.getByRole('table', { name: 'Active days to earn each shop reward' });
    expect(within(shop).getByRole('row', { name: /Practice outing.*51.*5.*Available/ })).toBeVisible();
    expect(within(shop).getByRole('row', { name: /Free family game.*0.*0.*Available/ })).toBeVisible();
    expect(screen.getByText(/10 Coins per dollar/)).toBeVisible();
  });

  it('separates saved activity from transactions, sources from transfers, and full-price estimates from balances', () => {
    renderWithProviders(<ProgressionObservations observations={evidence} />);
    expect(screen.getByRole('heading', { name: 'Observed family coin economy' })).toBeVisible();
    expect(screen.getByText(/All currently active children/)).toBeVisible();
    expect(screen.getByText('Active child-days with saved work')).toBeVisible();
    const sources = screen.getByRole('table', { name: 'Where Coin credits came from' });
    expect(within(sources).getByRole('row', { name: /Reading.*Regular earnings.*30.*6/ })).toBeVisible();
    expect(within(sources).getByRole('row', { name: /Birthdays.*Occasional bonus.*200.*1/ })).toBeVisible();
    expect(screen.getByText(/Small sample: fewer than 7 active child-days/)).toBeVisible();
    expect(screen.getByText(/240 Coins excluded/)).toBeVisible();
    const shop = screen.getByRole('table', { name: 'Active days to earn each shop reward' });
    expect(within(shop).getByRole('row', { name: /Practice outing.*51.*11.*Available/ })).toBeVisible();
    expect(within(shop).getByRole('row', { name: /Movie night.*100.*20.*Out of stock/ })).toBeVisible();
    expect(screen.getByText(/full price from zero/)).toBeVisible();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('shows zero-Coin activity and unavailable estimates without inventing a pace', () => {
    renderWithProviders(<ProgressionObservations observations={{ ...evidence, earning_pace: { ...evidence.earning_pace, status: 'insufficient_evidence', recurring_coins: 0, coins_per_active_day: null }, shop_rewards: [{ ...evidence.shop_rewards[0], days_to_earn: null }] }} />);
    expect(screen.getByText(/More saved activity and identified regular earnings are needed/)).toBeVisible();
    expect(within(screen.getByRole('table', { name: 'Active days to earn each shop reward' })).getByText('Unavailable')).toBeVisible();
    expect(screen.getByText('Active child-days with saved work')).toBeVisible();
  });

  it('keeps a historical recent-child checkpoint readable without fabricating new measurements', () => {
    const { earning_sources: _sources, earning_pace: _pace, shop_rewards: _shop, ...legacy } = evidence;
    renderWithProviders(<ProgressionObservations observations={{ ...legacy, cohort: { ...empty.cohort, registered_within_days: 90, scope: undefined }, activity: { ledger_active_children: 1, ledger_active_child_days: 2 } }} />);
    expect(screen.getByText(/accounts registered within 90 days/)).toBeVisible();
    expect(screen.getByText(/This saved report predates activity and shop estimates/)).toBeVisible();
    expect(screen.queryByRole('table', { name: 'Active days to earn each shop reward' })).not.toBeInTheDocument();
  });

  it('withholds partial source and shop results when a capacity limit is reached', () => {
    renderWithProviders(<ProgressionObservations observations={{ ...evidence, status: 'activity_limit_exceeded', earning_pace: { ...evidence.earning_pace, status: 'capacity_exceeded' } }} />);
    expect(screen.getByText(/Observation limits were reached/)).toBeVisible();
    expect(screen.queryByRole('table', { name: 'Active days to earn each shop reward' })).not.toBeInTheDocument();
    expect(screen.queryByText('Practice outing')).not.toBeInTheDocument();
  });
});

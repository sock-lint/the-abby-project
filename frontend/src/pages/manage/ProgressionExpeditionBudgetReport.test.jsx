import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import report from '../../../../contracts/api/fixtures/progression-lab-expedition-budget-report.json';
import comparison from '../../../../contracts/api/fixtures/progression-experiment-expedition-budget-comparison.json';
import ProgressionExpeditionBudgetReport from './ProgressionExpeditionBudgetReport';
import { ExperimentComparison } from './ProgressionExperimentEvidence';

describe('Shared expedition forecast', () => {
  it('shows actual server launch, item, pending and unavailable-path evidence', async () => {
    const { user } = renderWithProviders(<ProgressionExpeditionBudgetReport budget={report.expedition_budget} baseline={comparison.control.expedition_budget} />);
    expect(screen.getByRole('region', { name: 'Expedition budget forecast' })).toBeVisible();
    for (const label of ['Trips prevented by launch limit', 'Item slots withheld by limit', 'Item units awaiting claim', 'Trips promising no Coins or items']) expect(screen.getByRole('rowheader', { name: label })).toBeVisible();
    expect(screen.getByText(/Comparison limits: Unlimited expeditions/)).toBeVisible();
    expect(screen.getByText(/Removing access does not create additional content runway/)).toBeVisible();
    await user.click(screen.getByText('Expedition limit assumptions'));
    expect(screen.getByRole('list')).toBeVisible();
  });

  it('computes trip shares from means and avoids ratios of independent medians or zero launches', () => {
    const budget = { ...report.expedition_budget, summary: { ...report.expedition_budget.summary, launched_trips: { mean: 10, p50: 1 }, zero_coin_trips: { mean: 8, p50: 0 }, empty_trips: { mean: 2, p50: 0 } } };
    const { rerender } = renderWithProviders(<ProgressionExpeditionBudgetReport budget={budget} />);
    expect(screen.getByText(/Zero-direct-Coin trips: 80%. Completely empty trips: 20%/)).toBeVisible();
    rerender(<ProgressionExpeditionBudgetReport budget={{ ...budget, summary: { ...budget.summary, launched_trips: { mean: 0, p50: 0 } } }} />);
    expect(screen.getByText(/Zero-direct-Coin trips: Unavailable. Completely empty trips: Unavailable/)).toBeVisible();
  });

  it('labels a saved quota-only comparison with matching Coin rules and different expedition limits', () => {
    renderWithProviders(<ExperimentComparison comparison={comparison} dirty={false} />);
    const region = screen.getByRole('region', { name: 'Saved experiment comparison' });
    expect(within(region).getByText(/Control: 100-Coin commitment prototype.*Unlimited expeditions.*Candidate: 100-Coin commitment prototype.*1 launch \/ 1 item per child per day/)).toBeVisible();
    expect(within(region).getByRole('region', { name: 'Expedition budget forecast' })).toBeVisible();
    expect(within(region).getByRole('table', { name: 'Experiment success criteria' })).toBeVisible();
  });

  it('uses saved incubation timing and preserves legacy comparison bodies without inferring the current policy', () => {
    const policy = { duration_seconds: 86400, max_active: 1, clock: 'elapsed_seconds', start_strategy: 'first_compatible_pair_during_care', claim_strategy: 'next_active_care_visit_at_or_after_ready' };
    const saved = { ...comparison, control: { ...comparison.control, pet_incubation_policy: policy }, candidate: { ...comparison.candidate, pet_incubation_policy: policy } };
    const original = JSON.stringify(saved);
    const { rerender } = renderWithProviders(<ExperimentComparison comparison={saved} dirty={false} />);
    expect(within(screen.getByRole('region', { name: 'Recorded incubation policy' })).getByText('24 hours')).toBeVisible();
    expect(JSON.stringify(saved)).toBe(original);
    const legacy = JSON.parse(original);
    delete legacy.control.pet_incubation_policy;
    delete legacy.candidate.pet_incubation_policy;
    rerender(<ExperimentComparison comparison={legacy} dirty={false} />);
    expect(screen.getByText(/This report did not record an incubation policy/)).toBeVisible();
    expect(screen.queryByText('24 hours')).toBeNull();
    expect(legacy.candidate).not.toHaveProperty('pet_incubation_policy');
  });

  it('keeps older reports readable without invented expedition totals', () => {
    renderWithProviders(<ProgressionExpeditionBudgetReport />);
    expect(screen.queryByRole('region', { name: 'Expedition budget forecast' })).toBeNull();
  });
});

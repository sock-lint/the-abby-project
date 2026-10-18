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

  it('keeps older reports readable without invented expedition totals', () => {
    renderWithProviders(<ProgressionExpeditionBudgetReport />);
    expect(screen.queryByRole('region', { name: 'Expedition budget forecast' })).toBeNull();
  });
});

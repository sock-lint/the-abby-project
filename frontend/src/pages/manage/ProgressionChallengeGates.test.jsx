import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { selectDropdown } from '../../test/selectDropdown';
import ProgressionChallengeGateControls from './ProgressionChallengeGateControls';
import ProgressionChallengeGateReport from './ProgressionChallengeGateReport';
import { gateDefaults, gateMetadata, gateReport, gateRule } from './progressionChallengeGateTestData';
import { ExperimentComparison } from './ProgressionExperimentEvidence';
import milestoneComparison from '../../../../contracts/api/fixtures/progression-experiment-milestone-gates-comparison.json';
import tenureComparison from '../../../../contracts/api/fixtures/progression-experiment-tenure-gates-comparison.json';

function Controls({ changed, initial = gateDefaults, metadata = gateMetadata }) {
  const [gates, setGates] = useState(initial);
  return <ProgressionChallengeGateControls gates={gates} metadata={metadata} onChange={(value) => { setGates(value); changed(value); }} />;
}

describe('Challenge gate controls', () => {
  it('distinguishes same-name catalog definitions by ID in target and prerequisite choices', async () => {
    const changed = vi.fn();
    const metadata = { ...gateMetadata, challenge_gate_choices: { ...gateMetadata.challenge_gate_choices, quests: [...gateMetadata.challenge_gate_choices.quests, { id: 13, name: 'Next chapter', is_repeatable: false }] } };
    const { user } = renderWithProviders(<Controls changed={changed} metadata={metadata} initial={{ ...gateDefaults, rules: [{ ...gateRule }] }} />, { withAuth: false });
    const target = screen.getByRole('combobox', { name: 'Gate 1 challenge' });
    await user.click(target);
    expect(screen.getByRole('option', { name: 'Next chapter (#11)', exact: true })).toBeVisible();
    expect(screen.getByRole('option', { name: 'Next chapter (#13)', exact: true })).toBeVisible();
    await selectDropdown(user, target, 13);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Gate 1 previous challenge' }), 11);
    expect(changed.mock.lastCall[0].rules[0]).toMatchObject({ quest_id: 13, prerequisite_quest_id: 11 });
    expect(target).toHaveTextContent('Next chapter (#13)');
    expect(screen.getByRole('combobox', { name: 'Gate 1 previous challenge' })).toHaveTextContent('Next chapter (#11)');
    await selectDropdown(user, target, 11);
    expect(changed.mock.lastCall[0].rules[0]).toMatchObject({ quest_id: 11, prerequisite_quest_id: null });
  });
  it('edits catalog prerequisite, named skill, elapsed days and inclusive dates without applying live changes', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls changed={changed} />, { withAuth: false });
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Challenge gate policy' }), 'milestone_tenure');
    await user.click(screen.getByRole('button', { name: 'Add challenge gate' }));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Gate 1 challenge' }), 11);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Gate 1 previous challenge' }), 12);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Gate 1 skill' }), 7);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Gate 1 skill level' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Gate 1 elapsed days since first activity' }), { target: { value: '14' } });
    fireEvent.change(screen.getByLabelText('Gate 1 available from'), { target: { value: '2026-01-05' } });
    fireEvent.change(screen.getByLabelText('Gate 1 available until'), { target: { value: '2026-02-01' } });
    expect(changed.mock.lastCall[0]).toEqual({ ...gateDefaults, mode: 'milestone_tenure', rules: [{ ...gateRule, prerequisite_quest_id: 12 }] });
    expect(screen.getByText(/14 days unlocks on day 15/)).toBeVisible();
    expect(screen.getByText(/do not change live challenges or rewards/)).toBeVisible();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Challenge gate policy' }), 'current');
    expect(changed.mock.lastCall[0].rules[0]).toMatchObject({ min_days: 14, available_until: '2026-02-01' });
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Gate 1 skill' }), '');
    expect(changed.mock.lastCall[0].rules[0]).toMatchObject({ skill_id: null, skill_level: 0 });
    expect(screen.getByRole('spinbutton', { name: 'Gate 1 skill level' })).toBeDisabled();
  });
  it('bounds rules, excludes duplicate targets and repeatable targets, and removes only the chosen rule', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls changed={changed} metadata={{ ...gateMetadata, challenge_gates_limits: { max_rules: 1 } }} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add challenge gate' }));
    expect(screen.getByRole('button', { name: 'Add challenge gate' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Remove challenge gate 1' }));
    expect(changed.mock.lastCall[0].rules).toEqual([]);
    expect(screen.getByRole('button', { name: 'Add challenge gate' })).toBeEnabled();
  });
});

describe('Challenge gate evidence', () => {
  it('distinguishes same-name report targets without merging their results', () => {
    const first = gateReport.targets[0];
    renderWithProviders(<ProgressionChallengeGateReport gates={{ ...gateReport, targets: [first, { ...first, quest_id: 13, unlocked_trials: 0, completed_trials: 0, p50_unlock_days: null, p50_completion_days: null }] }} />, { withAuth: false });
    expect(screen.getByRole('row', { name: /Next chapter \(#11\)/ })).toHaveTextContent('Day 15');
    expect(within(screen.getByRole('row', { name: /Next chapter \(#13\)/ })).getAllByRole('cell', { name: 'Not reached' })).toHaveLength(2);
    expect(screen.getByText(/Locked, blocked and expired counts describe the end of the forecast/)).toBeVisible();
  });
  it.each([['milestone', milestoneComparison], ['tenure', tenureComparison]])('shows actual saved %s evidence with the current-rules control and recorded availability', (_name, comparison) => {
    renderWithProviders(<ExperimentComparison comparison={comparison} dirty={false} />, { withAuth: false });
    const panel = within(screen.getByRole('region', { name: 'Challenge gate forecast' }));
    expect(panel.getByText('Comparison policy: Current rules.')).toBeVisible();
    expect(panel.getByText(/Native modeled finite targets/)).toHaveTextContent(String(comparison.candidate.summary.finite_content_total));
    expect(screen.getByText(/Challenge policies: control uses Current challenge rules/)).toBeVisible();
    expect(panel.getByRole('rowheader', { name: 'Visits waiting for a future challenge gate' })).toBeVisible();
  });
  it('separates conditional timing, waiting, expiry and unreachable targets without treating waits as content', () => {
    renderWithProviders(<ProgressionChallengeGateReport gates={gateReport} baseline={{ ...gateReport, mode: 'current', visits: { waiting_for_gate_p50: 0 } }} />, { withAuth: false });
    expect(screen.getByText(/Comparison policy: Current rules/)).toBeVisible();
    expect(screen.getByText(/Reachable with these gates: 11/)).toBeVisible();
    expect(screen.getByText(/Gate waiting is not additional content/)).toBeVisible();
    const next = within(screen.getByRole('row', { name: /Next chapter/ }));
    expect(next.getByRole('cell', { name: 'Day 15' })).toBeVisible();
    expect(next.getByRole('cell', { name: 'Day 19' })).toBeVisible();
    expect(next.getByRole('cell', { name: '2 / 3' })).toBeVisible();
    expect(within(screen.getByRole('row', { name: /Later chapter/ })).getByText('prerequisite window expired')).toBeVisible();
    const blocked = within(screen.getByRole('row', { name: /First pages/ }));
    expect(blocked.getAllByRole('cell', { name: 'Not reached' })).toHaveLength(2);
    expect(blocked.getByText('availability closed')).toBeVisible();
  });
  it('omits the new panel for historical reports without a gate measurement', () => {
    renderWithProviders(<ProgressionChallengeGateReport />, { withAuth: false });
    expect(screen.queryByRole('region', { name: 'Challenge gate forecast' })).toBeNull();
  });
});

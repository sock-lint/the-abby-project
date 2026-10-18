import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PetIncubationPolicy from './PetIncubationPolicy';

const policy = {
  duration_seconds: 86400,
  max_active: 1,
  clock: 'elapsed_seconds',
  start_strategy: 'first_compatible_pair_during_care',
  claim_strategy: 'next_active_care_visit_at_or_after_ready',
};

describe('Lab incubation policy presentation', () => {
  it('explains the current server policy without fetching or exposing live actions', () => {
    const fetch = vi.spyOn(globalThis, 'fetch');
    render(<PetIncubationPolicy policy={policy} context="metadata" />);
    const panel = within(screen.getByRole('region', { name: 'Current model incubation policy' }));
    expect(panel.getByText('24 hours')).toBeVisible();
    expect(panel.getByText(/one unfinished egg at a time/)).toBeVisible();
    expect(panel.getByText(/first compatible egg and potion pair during care/)).toBeVisible();
    expect(panel.getByText(/next active care visit at or after the egg is ready/)).toBeVisible();
    expect(panel.getByText(/wait keeps running between visits/)).toBeVisible();
    expect(panel.getByText(/hatch claim adds the baby companion/)).toBeVisible();
    expect(panel.queryByRole('button')).toBeNull();
    expect(panel.queryByRole('textbox')).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockRestore();
  });

  it('keeps a report’s recorded wait separate from today’s model rules', () => {
    render(<>
      <PetIncubationPolicy policy={policy} context="metadata" />
      <PetIncubationPolicy policy={{ ...policy, duration_seconds: 7200 }} />
    </>);
    const current = within(screen.getByRole('region', { name: 'Current model incubation policy' }));
    const recorded = within(screen.getByRole('region', { name: 'Recorded incubation policy' }));
    expect(current.getByText('24 hours')).toBeVisible();
    expect(recorded.getByText('2 hours')).toBeVisible();
    expect(recorded.getByText('This policy was recorded with this report.')).toBeVisible();
    expect(recorded.queryByText('24 hours')).toBeNull();
  });

  it('keeps historical reports readable and explicitly unrecorded beside current rules', () => {
    render(<>
      <PetIncubationPolicy policy={policy} context="metadata" />
      <PetIncubationPolicy />
    </>);
    const recorded = within(screen.getByRole('region', { name: 'Recorded incubation policy' }));
    expect(recorded.getByRole('status')).toHaveTextContent('This report did not record an incubation policy. Its incubation wait and care strategy are unrecorded.');
    expect(recorded.queryByText('24 hours')).toBeNull();
    expect(recorded.queryByText(/one unfinished egg/)).toBeNull();
    expect(recorded.queryByText(/next active care visit/)).toBeNull();
    expect(recorded.queryByText('This policy was recorded with this report.')).toBeNull();
  });

  it('distinguishes unavailable current metadata from an unrecorded historical report', () => {
    render(<PetIncubationPolicy context="metadata" />);
    expect(screen.getByRole('status')).toHaveTextContent('The current model did not provide an incubation policy. Its incubation wait and care strategy are unavailable.');
    expect(screen.queryByText(/24 hours|This report did not record/)).toBeNull();
  });

  it('shows the exact recorded elapsed wait without rounding up to a different deadline', () => {
    render(<PetIncubationPolicy policy={{ ...policy, duration_seconds: 90061 }} />);
    expect(screen.getByText('25 hours 1 minute 1 second')).toBeVisible();
  });

  it.each([
    { ...policy, duration_seconds: '86400' },
    { ...policy, duration_seconds: -1 },
    { ...policy, clock: 'calendar_days' },
    { ...policy, max_active: 2 },
    { ...policy, start_strategy: 'automatic_hatch' },
    { ...policy, claim_strategy: 'automatic_hatch' },
    {},
  ])('leaves unsupported or incomplete recorded policies uninterpreted: %j', (recorded) => {
    render(<PetIncubationPolicy policy={recorded} />);
    expect(screen.getByRole('status')).toHaveTextContent('This report contains an incubation policy that this viewer cannot interpret. Its timing and care behavior are unavailable.');
    expect(screen.queryByText('24 hours')).toBeNull();
    expect(screen.queryByText(/one unfinished egg/)).toBeNull();
  });
});

import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PetIncubationJourney from './PetIncubationJourney';

const policy = { duration_seconds: 86400, max_active: 1, clock: 'elapsed_seconds',
  start_strategy: 'first_compatible_pair_during_care', claim_strategy: 'next_active_care_visit_at_or_after_ready' };

describe('Recorded incubation journey', () => {
  it('uses each receipt’s exact wait and ready day while retaining its recorded order', () => {
    render(<PetIncubationJourney policy={policy} events={[
      { day: 1, source: 'incubation_started', target: 'Chick', duration_seconds: 7200, ready_day: 2 },
      { day: 2, source: 'incubation_ready', target: 'Chick' },
      { day: 8, source: 'hatch', target: 'Chick' },
    ]} />);
    const rows = within(screen.getByRole('list', { name: 'Incubation journey events' })).getAllByRole('listitem');
    expect(rows[0]).toHaveTextContent('Incubation started');
    expect(rows[0]).toHaveTextContent('Recorded wait: 2 hours. Ready from Day 2.');
    expect(rows[1]).toHaveTextContent('Egg ready');
    expect(rows[1]).toHaveTextContent('next active care visit');
    expect(rows[2]).toHaveTextContent('Hatch claimed');
    expect(rows[2]).toHaveTextContent('Day 8');
    expect(rows[2]).toHaveTextContent('added the baby companion');
  });

  it('leaves absent receipt timing unrecorded even when the report has today’s policy', () => {
    render(<PetIncubationJourney policy={policy} events={[{ day: 1, source: 'incubation_started', target: 'Bat' }]} />);
    expect(screen.getByText('Recorded wait: Unrecorded. Ready day unrecorded.')).toBeVisible();
    expect(screen.queryByText(/24 hours|Day 2/)).toBeNull();
  });

  it('keeps a legacy hatch readable without inventing an incubation wait or claim strategy', () => {
    render(<PetIncubationJourney events={[{ day: 4, source: 'hatch', target: 'Bat' }]} />);
    expect(screen.getByText('Hatched companion')).toBeVisible();
    expect(screen.getByText('Day 4 · Bat')).toBeVisible();
    expect(screen.queryByText(/Hatch claimed|hours|Ready from|active care/)).toBeNull();
  });

  it('distinguishes an empty bounded preview from a complete journey with no incubations', () => {
    render(<PetIncubationJourney policy={policy} events={[{ day: 1, source: 'reading', xp: 5 }]} truncated />);
    expect(screen.getByText('No incubation or hatch events appear in this journey preview.')).toBeVisible();
    expect(screen.getByText('The journey preview is bounded and may omit events.')).toBeVisible();
    expect(screen.queryByRole('list')).toBeNull();
  });
});

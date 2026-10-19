import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PetIncubationState from './PetIncubationState';

describe('Recorded incubation counts', () => {
  it('keeps recorded zero counts separate from missing quantiles', () => {
    render(<PetIncubationState snapshot={{ day: 3, ready_eggs_p50: 0 }} />);
    const table = within(screen.getByRole('table', { name: 'Day 3 incubation state across simulated children' }));
    expect(within(table.getByRole('row', { name: /Ready eggs awaiting hatch/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Unrecorded', '0', 'Unrecorded']);
    expect(within(table.getByRole('row', { name: /Eggs incubating/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Unrecorded', 'Unrecorded', 'Unrecorded']);
  });

  it('shows separate group percentiles without summing them into one child’s capacity', () => {
    render(<PetIncubationState snapshot={{ day: 2, incubating_eggs_p10: 0, incubating_eggs_p50: 0, incubating_eggs_p90: 1, ready_eggs_p10: 0, ready_eggs_p50: 0, ready_eggs_p90: 1 }} />);
    const table = within(screen.getByRole('table', { name: 'Day 2 incubation state across simulated children' }));
    expect(within(table.getByRole('row', { name: /Eggs incubating/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['0', '0', '1']);
    expect(within(table.getByRole('row', { name: /Ready eggs awaiting hatch/ })).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['0', '0', '1']);
    expect(screen.getByText(/Percentiles in different rows can describe different simulated children/)).toBeVisible();
  });
});

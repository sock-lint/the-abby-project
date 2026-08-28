import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DueDateChips from './DueDateChips.jsx';
import { quickDueDates } from '../../utils/dates';

describe('DueDateChips', () => {
  it('renders the preset row', () => {
    render(<DueDateChips value="" onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: 'Tomorrow' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '+1 week' })).toBeInTheDocument();
  });

  it('reports the ISO date for the tapped chip', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<DueDateChips value="" onSelect={onSelect} />);
    await user.click(screen.getByRole('button', { name: 'Tomorrow' }));
    expect(onSelect).toHaveBeenCalledWith(quickDueDates().tomorrow);
  });

  it('marks the chip matching the current value as pressed', () => {
    render(<DueDateChips value={quickDueDates().tomorrow} onSelect={() => {}} />);
    expect(screen.getByRole('button', { name: 'Tomorrow' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '+1 week' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('never shows two chips for the same day', () => {
    render(<DueDateChips value="" onSelect={() => {}} />);
    const dates = screen.getAllByRole('button').map((b) => b.textContent);
    expect(new Set(dates).size).toBe(dates.length);
  });
});

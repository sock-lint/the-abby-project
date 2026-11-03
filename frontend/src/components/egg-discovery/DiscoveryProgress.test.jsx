import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { buildEggDiscovery } from '../../test/eggDiscoveries';
import DiscoveryProgress from './DiscoveryProgress';

describe('Ordinary discovery progress', () => {
  it.each([false, true])('keeps an unmet variety goal visible when one activity exceeds the time goal (compact=%s)', (compact) => {
    render(<DiscoveryProgress compact={compact} discovery={buildEggDiscovery({
      minutes: { reading: 600, movement: 0, practice: 0 },
    })} />);

    expect(screen.getByText('240 of 240 minutes recorded')).toBeInTheDocument();
    expect(screen.queryByText('600 of 240 minutes recorded')).toBeNull();
    expect(screen.getByText('1 of 2 activity types with at least 90 minutes')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Wolf Egg activity variety' })).toHaveAttribute('aria-valuenow', '1');
    expect(screen.getByRole('progressbar', { name: 'Wolf Egg activity variety' })).toHaveAttribute('aria-valuemax', '2');
    expect(screen.queryByText('Egg earned')).toBeNull();
    if (!compact) expect(screen.getByText('600 minutes')).toBeInTheDocument();
  });

  it.each([
    [{ reading: 60, movement: 60, practice: 120 }, 1],
    [{ reading: 90, movement: 90, practice: 60 }, 2],
    [{ reading: 90, movement: 90, practice: 90 }, 2],
  ])('counts only activity types meeting the saved minimum and caps the variety goal (%j)', (minutes, count) => {
    render(<DiscoveryProgress discovery={buildEggDiscovery({ minutes })} />);

    expect(screen.getByText(`${count} of 2 activity types with at least 90 minutes`)).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Wolf Egg activity variety' })).toHaveAttribute('aria-valuenow', String(count));
    expect(screen.queryByText('Egg earned')).toBeNull();
  });
});

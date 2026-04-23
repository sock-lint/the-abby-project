import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import IncipitBand from './IncipitBand';

function zeros() {
  return {
    common: { earned: 0, total: 0 },
    uncommon: { earned: 0, total: 0 },
    rare: { earned: 0, total: 0 },
    epic: { earned: 0, total: 0 },
    legendary: { earned: 0, total: 0 },
  };
}

describe('IncipitBand', () => {
  it('renders the codex heading, script kicker, and sealed count', () => {
    renderWithProviders(
      <IncipitBand
        earned={4}
        total={21}
        rarityCounts={{ ...zeros(), common: { earned: 2, total: 10 }, rare: { earned: 2, total: 5 } }}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Sigil Case' })).toBeInTheDocument();
    expect(screen.getByText(/the reliquary of seals/)).toBeInTheDocument();
    expect(screen.getByText('4 of 21')).toBeInTheDocument();
  });

  it('renders gracefully when the codex is empty (total === 0)', () => {
    renderWithProviders(<IncipitBand earned={0} total={0} rarityCounts={zeros()} />);
    expect(screen.getByText('0 of 0')).toBeInTheDocument();
    // Rarity strand still renders with its empty-state aria-label.
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'no seals catalogued');
  });
});

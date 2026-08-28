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
  it('renders the supplied title, kicker, and meta line', () => {
    renderWithProviders(
      <IncipitBand
        letter="S"
        title="Sigil Case"
        kicker="· the reliquary of seals ·"
        meta={
          <>
            <span className="tabular-nums">4 of 21</span>
            <span>sealed</span>
          </>
        }
        progressPct={20}
        rarityCounts={{
          ...zeros(),
          common: { earned: 2, total: 10 },
          rare: { earned: 2, total: 5 },
        }}
      />,
    );
    expect(screen.getByRole('heading', { name: 'Sigil Case' })).toBeInTheDocument();
    expect(screen.getByText(/the reliquary of seals/)).toBeInTheDocument();
    expect(screen.getByText('4 of 21')).toBeInTheDocument();
  });

  it('renders the rarity strand when rarityCounts is supplied', () => {
    renderWithProviders(
      <IncipitBand
        letter="S"
        title="Sigil Case"
        progressPct={0}
        rarityCounts={zeros()}
      />,
    );
    expect(screen.getByRole('img')).toHaveAttribute('aria-label', 'no seals catalogued');
  });

  it('omits the rarity strand when rarityCounts is not supplied', () => {
    renderWithProviders(
      <IncipitBand
        letter="J"
        title="Junior · 2025-26"
        kicker="· current chapter ·"
        progressPct={50}
      />,
    );
    // No role="img" since RarityStrand wasn't rendered.
    expect(screen.queryByRole('img')).toBeNull();
  });

  it('omits the kicker line when not supplied', () => {
    renderWithProviders(
      <IncipitBand letter="A" title="Chapter Alpha" progressPct={0} />,
    );
    expect(screen.getByRole('heading', { name: 'Chapter Alpha' })).toBeInTheDocument();
  });

  it('renders a responsive versal pair by default — md below sm, xl at sm+', () => {
    // Phone-aware default: the versal is a CSS-visibility pair so a 390px
    // phone gets the 48px drop-cap instead of the 96px one. jsdom renders
    // both; the visibility classes are the contract.
    const { container } = renderWithProviders(
      <IncipitBand letter="T" title="Trials" progressPct={30} />,
    );
    const versals = container.querySelectorAll('[data-versal="true"]');
    expect(versals).toHaveLength(2);
    expect(versals[0].classList.contains('sm:hidden')).toBe(true);
    expect(versals[0].className).toMatch(/w-12/); // md-size box
    expect(versals[1].classList.contains('hidden')).toBe(true);
    expect(versals[1].classList.contains('sm:inline-flex')).toBe(true);
    expect(versals[1].className).toMatch(/w-24/); // xl-size box
  });

  it('honors an explicitly-passed versalSize with a single fixed versal', () => {
    const { container } = renderWithProviders(
      <IncipitBand letter="H" title="Hoards" progressPct={40} versalSize="xl" />,
    );
    const versals = container.querySelectorAll('[data-versal="true"]');
    expect(versals).toHaveLength(1);
    expect(versals[0].className).toMatch(/w-24/);
    expect(versals[0].classList.contains('hidden')).toBe(false);
    expect(versals[0].classList.contains('sm:hidden')).toBe(false);
  });
});

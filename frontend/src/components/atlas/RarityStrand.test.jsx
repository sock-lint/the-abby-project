import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen } from '../../test/render';
import RarityStrand from './RarityStrand';

describe('RarityStrand', () => {
  it('renders as an img role with all five rarities in the aria-label', () => {
    const counts = {
      common: { earned: 1, total: 2 },
      uncommon: { earned: 0, total: 1 },
      rare: { earned: 3, total: 3 },
      epic: { earned: 0, total: 0 },
      legendary: { earned: 0, total: 1 },
    };
    renderWithProviders(<RarityStrand counts={counts} />);
    const strand = screen.getByRole('img');
    const label = strand.getAttribute('aria-label');
    expect(label).toMatch(/common/);
    expect(label).toMatch(/uncommon/);
    expect(label).toMatch(/rare/);
    expect(label).toMatch(/epic/);
    expect(label).toMatch(/legendary/);
    expect(label).toMatch(/4 of 7 sealed/);
  });

  it('renders an empty-state strand when no badges exist', () => {
    const counts = {
      common: { earned: 0, total: 0 },
      uncommon: { earned: 0, total: 0 },
      rare: { earned: 0, total: 0 },
      epic: { earned: 0, total: 0 },
      legendary: { earned: 0, total: 0 },
    };
    renderWithProviders(<RarityStrand counts={counts} />);
    const strand = screen.getByRole('img');
    expect(strand.getAttribute('aria-label')).toBe('no seals catalogued');
  });

  it('sizes each segment by rarity share of the total', () => {
    const counts = {
      common: { earned: 0, total: 2 },
      uncommon: { earned: 0, total: 0 },
      rare: { earned: 0, total: 2 },
      epic: { earned: 0, total: 0 },
      legendary: { earned: 0, total: 0 },
    };
    const { container } = renderWithProviders(<RarityStrand counts={counts} />);
    const segments = container.querySelectorAll('[data-rarity]');
    expect(segments.length).toBe(2);
    // common + rare split the strand 50/50 when each holds 2 of 4 total.
    segments.forEach((seg) => {
      expect(seg.style.width).toBe('50%');
    });
  });

  it('uses compact height when compact=true', () => {
    const counts = {
      common: { earned: 1, total: 1 },
      uncommon: { earned: 0, total: 0 },
      rare: { earned: 0, total: 0 },
      epic: { earned: 0, total: 0 },
      legendary: { earned: 0, total: 0 },
    };
    renderWithProviders(<RarityStrand counts={counts} compact />);
    const strand = screen.getByRole('img');
    expect(strand.className).toMatch(/\bh-1\b/);
  });
});

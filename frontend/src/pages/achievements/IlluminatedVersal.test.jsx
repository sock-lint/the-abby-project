import { describe, it, expect } from 'vitest';
import { renderWithProviders } from '../../test/render';
import IlluminatedVersal from './IlluminatedVersal';
import { PROGRESS_TIER } from './mastery.constants';

describe('IlluminatedVersal', () => {
  it('renders the first letter of the given string uppercased', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="mortise" progressPct={0} tier={PROGRESS_TIER.nascent} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    // The base layer carries the glyph; the gilt overlay carries the same glyph.
    expect(versal.textContent).toContain('M');
  });

  it('writes the progress percentage to the CSS variable on the wrapper', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="W" progressPct={42} tier={PROGRESS_TIER.rising} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.getAttribute('data-progress')).toBe('42');
    expect(versal.getAttribute('style')).toContain('--versal-fill');
    expect(versal.getAttribute('style')).toContain('42%');
  });

  it('is aria-hidden because the adjacent verse body carries semantic text', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="D" progressPct={50} tier={PROGRESS_TIER.rising} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).toHaveAttribute('aria-hidden', 'true');
  });

  it('applies a rarity halo ring for a gilded (mastered) skill', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="G" progressPct={100} tier={PROGRESS_TIER.gilded} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.className).toMatch(/ring-/);
    expect(versal.getAttribute('data-tier')).toBe('gilded');
  });

  it('applies a rarity halo ring for a cresting skill', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="C" progressPct={75} tier={PROGRESS_TIER.cresting} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.className).toMatch(/ring-/);
    expect(versal.getAttribute('data-tier')).toBe('cresting');
  });

  it('omits the halo ring for nascent (early) tiers', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="N" progressPct={10} tier={PROGRESS_TIER.nascent} />,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal.className).not.toMatch(/ring-/);
  });

  it('omits the gilt overlay when the versal is locked', () => {
    const { container } = renderWithProviders(
      <IlluminatedVersal letter="L" progressPct={0} tier={PROGRESS_TIER.locked} />,
    );
    const gilt = container.querySelector('[data-versal-gilt="true"]');
    expect(gilt).toBeNull();
  });
});

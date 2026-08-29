import { describe, it, expect } from 'vitest';
import { renderWithProviders } from '../../test/render';
import FolioHeadband from './FolioHeadband';

const band = (container) => container.querySelector('[data-folio-headband="true"]');

describe('FolioHeadband', () => {
  it('renders a decorative band carrying its tier on data-tier', () => {
    const { container } = renderWithProviders(<FolioHeadband tierKey="cresting" />);
    const el = band(container);
    expect(el).not.toBeNull();
    expect(el.getAttribute('data-tier')).toBe('cresting');
    expect(el.getAttribute('aria-hidden')).toBe('true');
  });

  it('maps all five tiers onto their own headband token', () => {
    // Pinned via data-tier + the token reference rather than a hex value, so
    // a palette retune stays free but a dropped tier stays loud.
    for (const key of ['locked', 'nascent', 'rising', 'cresting', 'gilded']) {
      const { container, unmount } = renderWithProviders(<FolioHeadband tierKey={key} />);
      const el = band(container);
      expect(el.getAttribute('data-tier'), `tier ${key} should render`).toBe(key);
      expect(el.style.backgroundColor).toBe(`var(--color-headband-${key})`);
      unmount();
    }
  });

  it('falls back to the locked tone for an unknown tier', () => {
    const { container } = renderWithProviders(<FolioHeadband tierKey="nonsense" />);
    expect(band(container).style.backgroundColor).toBe('var(--color-headband-locked)');
  });

  it('clears the card corner radius and ParchmentCard flourishes at both ends', () => {
    // The band used to be `top-0 left-0 right-0`, which buried the outer
    // stroke of the top corner flourishes (they sit at `top-1 left-1`) and
    // got sliced into a wedge by the card's rounded-xl + overflow-hidden.
    // Both terminals must stay inboard of that scrollwork.
    const { container } = renderWithProviders(<FolioHeadband tierKey="locked" />);
    const cls = band(container).className;
    expect(cls).toMatch(/\bleft-6\b/);
    expect(cls).toMatch(/\bright-6\b/);
    expect(cls).not.toMatch(/\bleft-0\b/);
  });

  it('spans to the gutter fold at md+, where the verso is its own column', () => {
    const { container } = renderWithProviders(<FolioHeadband tierKey="locked" />);
    expect(band(container).className).toMatch(/\bmd:right-0\b/);
  });

  it('carries the folio-headband class that masks its trailing end below md', () => {
    const { container } = renderWithProviders(<FolioHeadband tierKey="locked" />);
    expect(band(container).className).toMatch(/\bfolio-headband\b/);
  });
});

import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import QuestFolio from './QuestFolio';

function getVerso(container) {
  return container.querySelector('[data-folio-verso="true"]');
}

function getRecto(container) {
  return container.querySelector('[data-folio-recto="true"]');
}

describe('QuestFolio', () => {
  it('renders the title, kicker, and stats on the verso', () => {
    render(
      <QuestFolio
        letter="V"
        title="Ventures"
        kicker="the big adventures"
        stats={[
          { value: 3, label: 'in progress' },
          { value: 5, label: 'done' },
        ]}
        progressPct={62}
      >
        <p>recto body</p>
      </QuestFolio>,
    );
    // Title renders twice: once on the full md+ plate, once in the
    // compact phone header (jsdom renders both responsive variants).
    expect(screen.getAllByText('Ventures')).toHaveLength(2);
    expect(screen.getByText(/the big adventures/i)).toBeInTheDocument();
    // Each stat value renders twice for the same reason the title does — the
    // full plate's numeral and the compact row's. The compact row used to
    // inline them into one string; they are their own nodes now so the
    // numerals can carry tier.chip like the full plate's already do.
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/in progress/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/^done$/i).length).toBeGreaterThanOrEqual(1);
  });

  it('wears its tier as a kicker chip rather than an applied ornament', () => {
    // The folio used to carry a tier-tinted band across the top of the verso,
    // which was the only place in the app expressing state as applied
    // ornament. Tier now rides PROGRESS_TIER's own channels — one of them
    // being the kicker, rendered as a RuneBadge in the matching tone.
    const { container, rerender } = render(
      <QuestFolio letter="V" title="Ventures" kicker="the big adventures" progressPct={0}>
        x
      </QuestFolio>,
    );
    expect(container.querySelector('[data-folio-headband="true"]')).toBeNull();

    const chipOf = () => screen.getByText('the big adventures');
    // locked -> ink, cresting -> ember, gilded -> gold.
    expect(chipOf().className).toMatch(/ink-page-shadow|ink-secondary/);

    rerender(
      <QuestFolio letter="V" title="Ventures" kicker="the big adventures" progressPct={70}>
        x
      </QuestFolio>,
    );
    expect(chipOf().className).toMatch(/ember/);

    rerender(
      <QuestFolio letter="V" title="Ventures" kicker="the big adventures" progressPct={100}>
        x
      </QuestFolio>,
    );
    expect(chipOf().className).toMatch(/gold-leaf/);
  });

  it('renders consumer children on the recto', () => {
    const { container } = render(
      <QuestFolio letter="D" title="Duties" progressPct={0}>
        <div data-testid="recto-content">working list</div>
      </QuestFolio>,
    );
    const recto = getRecto(container);
    expect(recto).not.toBeNull();
    expect(recto).toContainElement(screen.getByTestId('recto-content'));
    expect(recto).toHaveTextContent('working list');
  });

  it('sets data-tier from progressPct on the verso', () => {
    const { container, rerender } = render(
      <QuestFolio letter="A" title="A" progressPct={0}>x</QuestFolio>,
    );
    // 0% with unlocked=false → locked tier.
    expect(getVerso(container)).toHaveAttribute('data-tier', 'locked');
    expect(getVerso(container)).toHaveAttribute('data-progress', '0');

    rerender(<QuestFolio letter="A" title="A" progressPct={30}>x</QuestFolio>);
    expect(getVerso(container)).toHaveAttribute('data-tier', 'rising');
    expect(getVerso(container)).toHaveAttribute('data-progress', '30');

    rerender(<QuestFolio letter="A" title="A" progressPct={70}>x</QuestFolio>);
    expect(getVerso(container)).toHaveAttribute('data-tier', 'cresting');

    rerender(<QuestFolio letter="A" title="A" progressPct={95}>x</QuestFolio>);
    expect(getVerso(container)).toHaveAttribute('data-tier', 'gilded');
  });

  it('renders a progressbar with the correct aria-valuenow when progressPct > 0', () => {
    render(
      <QuestFolio letter="S" title="Study" progressPct={42}>x</QuestFolio>,
    );
    // One bar on the full md+ plate, one in the compact phone header —
    // CSS shows exactly one per breakpoint but jsdom renders both.
    const bars = screen.getAllByRole('progressbar', { name: /study progress/i });
    expect(bars).toHaveLength(2);
    bars.forEach((bar) => {
      expect(bar).toHaveAttribute('aria-valuenow', '42');
      expect(bar).toHaveAttribute('aria-valuemin', '0');
      expect(bar).toHaveAttribute('aria-valuemax', '100');
    });
  });

  it('renders a compact phone header inside the verso alongside the full plate', () => {
    const { container } = render(
      <QuestFolio
        letter="D"
        title="Duties"
        kicker="the daily keep"
        stats={[
          { value: 12, label: 'done' },
          { value: 3, label: 'waiting' },
        ]}
        progressPct={80}
        progressLabel="12 of 15 sealed"
      >
        x
      </QuestFolio>,
    );
    const compact = container.querySelector('[data-folio-verso-compact="true"]');
    expect(compact).not.toBeNull();
    // Compact row shows only below md; the full plate only at md+.
    expect(compact.className).toContain('md:hidden');
    const full = container.querySelector('[data-folio-verso-full="true"]');
    expect(full).not.toBeNull();
    expect(full.className).toContain('hidden');
    expect(full.className).toContain('md:flex');
    // Compact row mirrors the tier/progress data attributes.
    expect(compact).toHaveAttribute('data-tier', 'cresting');
    expect(compact).toHaveAttribute('data-progress', '80');
    // Small versal + title + inlined stats caption + progress label.
    expect(compact.querySelector('[data-versal="true"]')).not.toBeNull();
    expect(compact).toHaveTextContent('Duties');
    expect(compact).toHaveTextContent('12 done · 3 waiting');
    expect(compact).toHaveTextContent('12 of 15 sealed');
    // The compact progress bar carries real progressbar semantics.
    const bar = compact.querySelector('[role="progressbar"]');
    expect(bar).not.toBeNull();
    expect(bar).toHaveAttribute('aria-valuenow', '80');
    // The ornament stays out of the compact row: kicker + medallion live
    // only on the full plate.
    expect(compact.textContent).not.toContain('the daily keep');
    expect(compact.querySelector('[data-folio-medallion="true"]')).toBeNull();
    expect(full.querySelector('[data-folio-medallion="true"]')).not.toBeNull();
  });

  it('omits RarityStrand when rarityCounts is not provided', () => {
    const { container } = render(
      <QuestFolio letter="R" title="Rituals" progressPct={20}>x</QuestFolio>,
    );
    expect(container.querySelector('[data-rarity]')).toBeNull();
  });

  it('renders RarityStrand when rarityCounts is provided', () => {
    const { container } = render(
      <QuestFolio
        letter="V"
        title="Ventures"
        progressPct={50}
        rarityCounts={{
          common: { earned: 1, total: 2 },
          uncommon: { earned: 0, total: 1 },
          rare: { earned: 0, total: 0 },
          epic: { earned: 0, total: 0 },
          legendary: { earned: 0, total: 0 },
        }}
      >
        x
      </QuestFolio>,
    );
    // RarityStrand paints a data-rarity attr per non-empty segment.
    expect(container.querySelector('[data-rarity="common"]')).not.toBeNull();
    expect(container.querySelector('[data-rarity="uncommon"]')).not.toBeNull();
  });

  it('clamps off-scale progressPct values', () => {
    const { container, rerender } = render(
      <QuestFolio letter="X" title="X" progressPct={-50}>x</QuestFolio>,
    );
    expect(getVerso(container)).toHaveAttribute('data-progress', '0');

    rerender(<QuestFolio letter="X" title="X" progressPct={200}>x</QuestFolio>);
    expect(getVerso(container)).toHaveAttribute('data-progress', '100');
  });

  it('uses the first character of letter (or title fallback) as the drop-cap', () => {
    const { container, rerender } = render(
      <QuestFolio letter="abc" title="Anything" progressPct={0}>x</QuestFolio>,
    );
    const versal = container.querySelector('[data-versal="true"]');
    expect(versal).not.toBeNull();
    // Letter prop took precedence; the primitive uppercases its first char.
    expect(versal.textContent).toContain('A');

    rerender(<QuestFolio title="Ventures" progressPct={0}>x</QuestFolio>);
    expect(container.querySelector('[data-versal="true"]').textContent).toContain('V');
  });
});

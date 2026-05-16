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
    expect(screen.getByText('Ventures')).toBeInTheDocument();
    expect(screen.getByText(/the big adventures/i)).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/in progress/i)).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText(/^done$/i)).toBeInTheDocument();
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
    const bar = screen.getByRole('progressbar', { name: /study progress/i });
    expect(bar).toHaveAttribute('aria-valuenow', '42');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
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

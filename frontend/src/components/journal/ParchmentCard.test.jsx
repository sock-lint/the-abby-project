import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ParchmentCard from './ParchmentCard.jsx';

describe('ParchmentCard', () => {
  it('reserves a separate content region for the two decorative storybook corners', () => {
    const { container } = render(<ParchmentCard flourish="storybook"><h2>A long project title</h2><button>Continue</button></ParchmentCard>);
    const content = container.querySelector('[data-storybook-content]');
    expect(content).toContainElement(screen.getByRole('heading'));
    expect(content).toContainElement(screen.getByRole('button', { name: 'Continue' }));
    const corners = container.querySelectorAll('[data-storybook-corner]');
    expect(corners).toHaveLength(2);
    for (const corner of corners) {
      expect(corner).toHaveAttribute('aria-hidden', 'true');
      expect(content).not.toContainElement(corner);
    }
  });

  it('renders children', () => {
    render(<ParchmentCard>hi</ParchmentCard>);
    expect(screen.getByText('hi')).toBeInTheDocument();
  });

  it('applies default plain/default variant classes', () => {
    const { container } = render(<ParchmentCard>x</ParchmentCard>);
    expect(container.firstChild.className).toContain('bg-ink-page-aged');
    expect(container.firstChild.className).toContain('border');
  });

  it('applies deckle variant class', () => {
    const { container } = render(<ParchmentCard variant="deckle">x</ParchmentCard>);
    expect(container.firstChild.className).toContain('deckle-edge');
  });

  it('applies sealed variant class', () => {
    const { container } = render(<ParchmentCard variant="sealed">x</ParchmentCard>);
    expect(container.firstChild.className).toContain('rounded-xl');
  });

  it('applies bright tone class', () => {
    const { container } = render(<ParchmentCard tone="bright">x</ParchmentCard>);
    expect(container.firstChild.className).toContain('bg-ink-page-rune-glow');
  });

  it('applies deep tone class', () => {
    const { container } = render(<ParchmentCard tone="deep">x</ParchmentCard>);
    expect(container.firstChild.className).toContain('bg-ink-page-shadow/80');
  });

  it('keeps card accents decorative when flourish=true', () => {
    const { container } = render(<ParchmentCard flourish>x</ParchmentCard>);
    expect(container.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThanOrEqual(4);
  });

  it('keeps the optional corner accent decorative when seal=true', () => {
    const { container } = render(<ParchmentCard seal>x</ParchmentCard>);
    const seals = container.querySelectorAll('[aria-hidden="true"]');
    expect(seals.length).toBeGreaterThan(0);
  });

  it('accepts seal position as a string', () => {
    const { container } = render(<ParchmentCard seal="bottom-left">x</ParchmentCard>);
    expect(container.innerHTML).toContain('bottom-2 left-2');
  });

  it('falls back to top-right when seal position is unknown', () => {
    const { container } = render(<ParchmentCard seal="nowhere">x</ParchmentCard>);
    expect(container.innerHTML).toContain('top-2 right-2');
  });

  it('renders a custom tag via as= prop', () => {
    const { container } = render(<ParchmentCard as="section">x</ParchmentCard>);
    expect(container.querySelector('section')).toBeTruthy();
  });

  it('forwards refs', () => {
    let captured = null;
    const Fwd = () => <ParchmentCard ref={(el) => { captured = el; }}>x</ParchmentCard>;
    render(<Fwd />);
    expect(captured).toBeTruthy();
  });
});

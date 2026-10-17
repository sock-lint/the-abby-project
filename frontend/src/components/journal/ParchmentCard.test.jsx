import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import ParchmentCard from './ParchmentCard.jsx';

describe('ParchmentCard', () => {
  it.each([{ flourish: true }, { flourish: 'storybook' }, { seal: true }, { seal: 'bottom-left' }, { flourish: true, seal: true }])('accepts legacy decoration props without adding ornaments: %j', (legacyProps) => {
    const { container } = render(<ParchmentCard {...legacyProps} className="space-y-4"><h2>A long project title</h2><button>Continue</button></ParchmentCard>);
    const card = container.firstChild;
    expect(screen.getByRole('heading').parentElement).toBe(card);
    expect(screen.getByRole('button', { name: 'Continue' }).parentElement).toBe(card);
    expect(card.children).toHaveLength(2);
    expect(card).not.toHaveAttribute('flourish');
    expect(card).not.toHaveAttribute('seal');
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

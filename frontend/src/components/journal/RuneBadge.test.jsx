import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import RuneBadge from './RuneBadge.jsx';

describe('RuneBadge', () => {
  it('renders children', () => {
    render(<RuneBadge>New</RuneBadge>);
    expect(screen.getByText('New')).toBeInTheDocument();
  });

  it.each([
    ['teal', 'sheikah-teal'],
    ['moss', 'moss'],
    ['ember', 'ember'],
    ['royal', 'royal'],
    ['gold', 'gold-leaf'],
    ['ink', 'ink-page-shadow'],
    ['rose', 'rose'],
  ])('applies %s tone class', (tone, cls) => {
    const { container } = render(<RuneBadge tone={tone}>t</RuneBadge>);
    expect(container.firstChild.className).toContain(cls);
  });

  it('falls back to teal for unknown tones', () => {
    const { container } = render(<RuneBadge tone="unknown">t</RuneBadge>);
    expect(container.firstChild.className).toContain('sheikah-teal');
  });

  it('applies outlined variant classes', () => {
    const { container } = render(<RuneBadge variant="outlined">t</RuneBadge>);
    expect(container.firstChild.className).not.toContain('bg-sheikah-teal/20');
  });

  it('applies md size class', () => {
    const { container } = render(<RuneBadge size="md">t</RuneBadge>);
    expect(container.firstChild.className).toContain('text-xs');
  });

  it('falls back to sm size for unknown size', () => {
    const { container } = render(<RuneBadge size="xl">t</RuneBadge>);
    expect(container.firstChild.className).toContain('text-tiny');
  });

  it('renders icon slot', () => {
    render(<RuneBadge icon={<svg data-testid="icn" />}>t</RuneBadge>);
    expect(screen.getByTestId('icn')).toBeInTheDocument();
  });

  it('accepts a custom className', () => {
    const { container } = render(<RuneBadge className="extra">t</RuneBadge>);
    expect(container.firstChild.className).toContain('extra');
  });
});

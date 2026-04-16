import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import Card from './Card.jsx';

describe('Card', () => {
  it('renders children inside a ParchmentCard', () => {
    render(<Card>hello</Card>);
    expect(screen.getByText('hello')).toBeInTheDocument();
  });

  it('passes className through to the underlying card', () => {
    const { container } = render(<Card className="extra-class">x</Card>);
    expect(container.firstChild.className).toContain('extra-class');
  });

  it('forwards other props', () => {
    const { container } = render(<Card data-testid="card">x</Card>);
    expect(container.firstChild.getAttribute('data-testid')).toBe('card');
  });
});

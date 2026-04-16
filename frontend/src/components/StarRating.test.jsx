import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import StarRating from './StarRating.jsx';

describe('StarRating', () => {
  it('renders filled plus empty stars to the configured max', () => {
    const { container } = render(<StarRating value={3} max={5} />);
    expect(container.textContent).toBe('★★★☆☆');
  });

  it('clamps value above max', () => {
    const { container } = render(<StarRating value={7} max={5} />);
    expect(container.textContent).toBe('★★★★★');
  });

  it('clamps negative values to zero', () => {
    const { container } = render(<StarRating value={-2} max={3} />);
    expect(container.textContent).toBe('☆☆☆');
  });

  it('uses default max when omitted', () => {
    const { container } = render(<StarRating value={0} />);
    expect(container.textContent.length).toBe(5);
  });

  it('applies title attribute when provided', () => {
    render(<StarRating value={1} title="Difficulty" />);
    expect(screen.getByTitle('Difficulty')).toBeInTheDocument();
  });

  it('accepts a custom className', () => {
    const { container } = render(<StarRating value={1} className="extra" />);
    expect(container.firstChild.className).toContain('extra');
  });
});

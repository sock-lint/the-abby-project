import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import Sparkline from './Sparkline.jsx';

describe('Sparkline', () => {
  it('renders an accessible svg with one point per datum', () => {
    render(<Sparkline data={[0, 5, 3]} label="coins earned, last 3 days" />);
    const svg = screen.getByRole('img', { name: /coins earned/i });
    const points = svg.querySelector('polyline').getAttribute('points');
    expect(points.split(' ')).toHaveLength(3);
  });

  it('scales the peak to the top and zeros to the bottom', () => {
    render(<Sparkline data={[0, 10]} label="trend" />);
    const points = screen.getByRole('img').querySelector('polyline')
      .getAttribute('points').split(' ');
    const [, y0] = points[0].split(',').map(Number);
    const [, y1] = points[1].split(',').map(Number);
    expect(y0).toBeGreaterThan(y1); // SVG y grows downward
    expect(y1).toBe(2); // peak sits at top padding
  });

  it('paints a flat baseline for all-zero data', () => {
    render(<Sparkline data={[0, 0, 0]} label="trend" />);
    const ys = new Set(
      screen.getByRole('img').querySelector('polyline')
        .getAttribute('points').split(' ')
        .map((p) => p.split(',')[1]),
    );
    expect(ys.size).toBe(1);
  });

  it('renders nothing without data', () => {
    const { container } = render(<Sparkline data={[]} label="trend" />);
    expect(container).toBeEmptyDOMElement();
  });
});

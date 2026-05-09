import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import SparkleBurst from './SparkleBurst';

describe('SparkleBurst', () => {
  it('renders N motion divs and is hidden from a11y tree', () => {
    const { container } = render(<SparkleBurst count={6} radius={80} />);
    const root = container.firstChild;
    expect(root).not.toBeNull();
    expect(root.getAttribute('aria-hidden')).toBe('true');
    // Each sparkle is a positioned <div>; with count=6 we expect 6 children.
    expect(root.children.length).toBe(6);
  });

  it('defaults to 8 sparkles', () => {
    const { container } = render(<SparkleBurst />);
    expect(container.firstChild.children.length).toBe(8);
  });
});

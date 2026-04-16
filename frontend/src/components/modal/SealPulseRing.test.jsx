import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import SealPulseRing from './SealPulseRing.jsx';

describe('SealPulseRing', () => {
  it('applies default rounded class', () => {
    const { container } = render(<SealPulseRing />);
    expect(container.firstChild.className).toContain('rounded-2xl');
  });

  it('accepts custom rounded class', () => {
    const { container } = render(<SealPulseRing rounded="rounded-full" />);
    expect(container.firstChild.className).toContain('rounded-full');
  });

  it('accepts extra className', () => {
    const { container } = render(<SealPulseRing className="extra" />);
    expect(container.firstChild.className).toContain('extra');
  });

  it('is aria-hidden', () => {
    const { container } = render(<SealPulseRing />);
    expect(container.firstChild.getAttribute('aria-hidden')).toBe('true');
  });
});

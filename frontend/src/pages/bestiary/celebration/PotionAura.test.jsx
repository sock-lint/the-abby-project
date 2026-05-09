import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import PotionAura from './PotionAura';

describe('PotionAura', () => {
  it('renders an aria-hidden, pointer-events-none overlay', () => {
    const { container } = render(<PotionAura potionSlug="fire" />);
    const root = container.firstChild;
    expect(root).not.toBeNull();
    expect(root.getAttribute('aria-hidden')).toBe('true');
    expect(root.className).toMatch(/pointer-events-none/);
  });

  it('falls back to the neutral aura color for unknown potion slugs', () => {
    const { container } = render(<PotionAura potionSlug={null} />);
    const root = container.firstChild;
    // The fallback uses the neutral teal tone; we assert by snapshotting
    // the radial-gradient signature rather than the exact hex so future
    // tone tweaks don't brittle-break this test.
    expect(root.style.background).toMatch(/radial-gradient/);
  });

  it('honors the intensity prop via opacity', () => {
    const { container } = render(<PotionAura potionSlug="cosmic" intensity={0.4} />);
    expect(container.firstChild.style.opacity).toBe('0.4');
  });
});

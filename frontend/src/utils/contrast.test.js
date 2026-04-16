import { describe, it, expect } from 'vitest';
import { hexToRgb, relativeLuminance, contrastRatio } from './contrast';

describe('hexToRgb', () => {
  it('parses a full 6-char hex', () => {
    expect(hexToRgb('#ff8040')).toEqual({ r: 255, g: 128, b: 64 });
  });

  it('parses a 3-char shorthand hex', () => {
    expect(hexToRgb('#f84')).toEqual({ r: 255, g: 136, b: 68 });
  });

  it('accepts hex without a leading #', () => {
    expect(hexToRgb('000000')).toEqual({ r: 0, g: 0, b: 0 });
  });
});

describe('relativeLuminance', () => {
  it('returns 0 for pure black', () => {
    expect(relativeLuminance('#000000')).toBeCloseTo(0, 5);
  });

  it('returns 1 for pure white', () => {
    expect(relativeLuminance('#ffffff')).toBeCloseTo(1, 5);
  });

  it('uses the linear-segment branch for very dark channels', () => {
    // sRGB ≤ 0.03928 uses sRGB/12.92 (linear), not the gamma curve.
    // #0a0a0a = 10/255 ≈ 0.0392 sits right at the boundary.
    const lum = relativeLuminance('#0a0a0a');
    expect(lum).toBeGreaterThan(0);
    expect(lum).toBeLessThan(0.01);
  });
});

describe('contrastRatio', () => {
  it('gives 21:1 for black on white', () => {
    expect(contrastRatio('#000000', '#ffffff')).toBeCloseTo(21, 1);
  });

  it('is symmetric (swap fg/bg returns the same ratio)', () => {
    const a = contrastRatio('#2d1f15', '#f4ecd8');
    const b = contrastRatio('#f4ecd8', '#2d1f15');
    expect(a).toBeCloseTo(b, 5);
  });

  it('returns 1:1 for identical colors', () => {
    expect(contrastRatio('#888888', '#888888')).toBeCloseTo(1, 5);
  });

  it('clears the WCAG AA threshold for the Hyrule primary-on-page pairing', () => {
    // Concrete regression check: the shipped ink/page values must pass.
    expect(contrastRatio('#2d1f15', '#f4ecd8')).toBeGreaterThanOrEqual(4.5);
  });
});

import { describe, expect, it } from 'vitest';
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDuration,
} from './format.js';

describe('formatCurrency', () => {
  it('formats a decimal number with two decimals', () => {
    expect(formatCurrency(12.5)).toBe('$12.50');
  });

  it('formats a string number', () => {
    expect(formatCurrency('3')).toBe('$3.00');
  });

  it('returns $0.00 for non-numeric input', () => {
    expect(formatCurrency('not-a-number')).toBe('$0.00');
    expect(formatCurrency(NaN)).toBe('$0.00');
  });

  it('formats zero', () => {
    expect(formatCurrency(0)).toBe('$0.00');
  });
});

describe('formatDuration', () => {
  it('splits minutes into hours and minutes', () => {
    expect(formatDuration(125)).toBe('2h 5m');
  });

  it('handles zero', () => {
    expect(formatDuration(0)).toBe('0h 0m');
  });

  it('handles undefined as zero', () => {
    expect(formatDuration(undefined)).toBe('0h 0m');
  });

  it('handles non-numeric strings as zero', () => {
    expect(formatDuration('abc')).toBe('0h 0m');
  });

  it('formats exact hours', () => {
    expect(formatDuration(60)).toBe('1h 0m');
  });
});

describe('formatDate', () => {
  it('returns empty string for falsy input', () => {
    expect(formatDate('')).toBe('');
    expect(formatDate(null)).toBe('');
    expect(formatDate(undefined)).toBe('');
  });

  it('returns a locale date for a valid ISO string', () => {
    expect(formatDate('2026-04-16T00:00:00Z')).not.toBe('');
  });
});

describe('formatDateTime', () => {
  it('returns empty string for falsy input', () => {
    expect(formatDateTime(null)).toBe('');
  });

  it('returns a locale datetime for a valid ISO string', () => {
    expect(formatDateTime('2026-04-16T12:34:00Z')).not.toBe('');
  });
});

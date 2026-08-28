import { describe, expect, it } from 'vitest';
import {
  formatCurrency,
  formatDate,
  formatDateTime,
  formatDuration,
  formatMonth,
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

  // Sub-hour values drop the "0h" so the header clock pip, the hero card and
  // the timecard rows can all share this one formatter without reading as
  // "0h 45m" — the pip used to hand-roll "45m"/"1h 05" instead.
  it('omits the hour part under an hour', () => {
    expect(formatDuration(45)).toBe('45m');
  });

  it('handles zero', () => {
    expect(formatDuration(0)).toBe('0m');
  });

  it('handles undefined as zero', () => {
    expect(formatDuration(undefined)).toBe('0m');
  });

  it('handles non-numeric strings as zero', () => {
    expect(formatDuration('abc')).toBe('0m');
  });

  it('formats exact hours', () => {
    expect(formatDuration(60)).toBe('1h 0m');
  });

  it('does not pad the minute part past the hour', () => {
    expect(formatDuration(65)).toBe('1h 5m');
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

  // DRF DateField sends a bare "YYYY-MM-DD". new Date() reads that as UTC
  // midnight, which is the evening BEFORE in America/Phoenix — so timecards
  // labelled themselves "week of" Saturday and duties showed yesterday.
  it('keeps a date-only string on its own calendar day', () => {
    const d = new Date(2026, 3, 16);
    expect(formatDate('2026-04-16')).toBe(d.toLocaleDateString());
  });

  it('keeps a date-only string on its own day across a month boundary', () => {
    const d = new Date(2026, 0, 1);
    expect(formatDate('2026-01-01')).toBe(d.toLocaleDateString());
  });
});

describe('formatMonth', () => {
  it('keeps a date-only string in its own month', () => {
    const d = new Date(2026, 0, 1);
    expect(formatMonth('2026-01-01')).toBe(
      d.toLocaleDateString(undefined, { year: 'numeric', month: 'long' }),
    );
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

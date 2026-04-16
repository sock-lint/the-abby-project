import { describe, it, expect } from 'vitest';
import { toISODate, quickDueDates } from './dates';

describe('toISODate', () => {
  it('returns local YYYY-MM-DD (not UTC-shifted)', () => {
    // 11:30 PM local on Jan 15 — in UTC+ zones this rolls to Jan 16 via toISOString.
    const d = new Date(2026, 0, 15, 23, 30);
    expect(toISODate(d)).toBe('2026-01-15');
  });

  it('zero-pads month and day', () => {
    expect(toISODate(new Date(2026, 2, 5))).toBe('2026-03-05');
  });
});

describe('quickDueDates', () => {
  it('tomorrow is today + 1 day', () => {
    const wed = new Date(2026, 3, 15); // Wed 2026-04-15
    expect(quickDueDates(wed).tomorrow).toBe('2026-04-16');
  });

  it('friday returns this-week Friday when seeded with a Wednesday', () => {
    const wed = new Date(2026, 3, 15); // Wed 2026-04-15
    expect(quickDueDates(wed).friday).toBe('2026-04-17');
  });

  it('friday jumps to next-week Friday when seeded with a Saturday', () => {
    const sat = new Date(2026, 3, 18); // Sat 2026-04-18
    expect(quickDueDates(sat).friday).toBe('2026-04-24');
  });

  it('friday jumps to next-week Friday when seeded with Friday itself', () => {
    const fri = new Date(2026, 3, 17); // Fri 2026-04-17
    expect(quickDueDates(fri).friday).toBe('2026-04-24');
  });

  it('nextMonday is always a future Monday (from Monday → +7)', () => {
    const mon = new Date(2026, 3, 13); // Mon 2026-04-13
    expect(quickDueDates(mon).nextMonday).toBe('2026-04-20');
  });

  it('nextMonday from Sunday is tomorrow', () => {
    const sun = new Date(2026, 3, 19); // Sun 2026-04-19
    expect(quickDueDates(sun).nextMonday).toBe('2026-04-20');
  });

  it('nextWeek is today + 7 days', () => {
    const wed = new Date(2026, 3, 15);
    expect(quickDueDates(wed).nextWeek).toBe('2026-04-22');
  });
});

import { describe, expect, it } from 'vitest';
import { nextDueTarget } from './_dashboardShared';

function makeDate(year, month, day) {
  // month is 1-indexed here for readability.
  return new Date(year, month - 1, day);
}

describe('nextDueTarget', () => {
  it('targets tomorrow on Mon–Thu', () => {
    // 2026-04-13 is a Monday.
    expect(nextDueTarget(makeDate(2026, 4, 13))).toMatchObject({ iso: '2026-04-14', label: 'tomorrow' });
    // Wednesday → Thursday
    expect(nextDueTarget(makeDate(2026, 4, 15))).toMatchObject({ iso: '2026-04-16', label: 'tomorrow' });
    // Thursday → Friday
    expect(nextDueTarget(makeDate(2026, 4, 16))).toMatchObject({ iso: '2026-04-17', label: 'tomorrow' });
  });

  it('targets next Monday on Fri / Sat / Sun', () => {
    // 2026-04-17 is a Friday → Monday 2026-04-20
    expect(nextDueTarget(makeDate(2026, 4, 17))).toMatchObject({ iso: '2026-04-20', label: 'Monday' });
    // Saturday → Monday
    expect(nextDueTarget(makeDate(2026, 4, 18))).toMatchObject({ iso: '2026-04-20', label: 'Monday' });
    // Sunday → Monday
    expect(nextDueTarget(makeDate(2026, 4, 19))).toMatchObject({ iso: '2026-04-20', label: 'Monday' });
  });

  it('crosses month boundaries correctly', () => {
    // Thursday 2026-04-30 → Friday 2026-05-01
    expect(nextDueTarget(makeDate(2026, 4, 30))).toMatchObject({ iso: '2026-05-01', label: 'tomorrow' });
    // Friday 2026-05-29 → Monday 2026-06-01
    expect(nextDueTarget(makeDate(2026, 5, 29))).toMatchObject({ iso: '2026-06-01', label: 'Monday' });
  });
});

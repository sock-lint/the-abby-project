import { describe, expect, it } from 'vitest';
import { choreReminderEvent, nextChoreReminderDate, validateChoreReminderDate } from './choresCalendar';

describe('duty reminder dates', () => {
  it('offers today for regular duties and does not invent a weekly deadline', () => {
    expect(nextChoreReminderDate({ recurrence: 'weekly' }, '2026-10-11')).toBe('2026-10-11');
    expect(nextChoreReminderDate({ recurrence: 'one_time' }, '2026-10-11')).toBe('2026-10-11');
  });

  it('uses the next active day rather than the custody reference date', () => {
    const chore = { week_schedule: 'alternating', schedule_start_date: '2026-10-05' };
    expect(nextChoreReminderDate(chore, '2026-10-12')).toBe('2026-10-19');
    expect(nextChoreReminderDate(chore, '2026-10-06')).toBe('2026-10-06');
  });

  it('matches ISO week parity through a 53-week year instead of repeating every 14 days', () => {
    const evenWeek = { week_schedule: 'alternating', schedule_start_date: '2020-12-21' };
    const oddWeek = { week_schedule: 'alternating', schedule_start_date: '2020-12-28' };
    expect(nextChoreReminderDate(evenWeek, '2020-12-28')).toBe('2021-01-11');
    expect(nextChoreReminderDate(oddWeek, '2021-01-04')).toBe('2021-01-04');
    expect(validateChoreReminderDate(evenWeek, '2021-01-04')).toMatch(/off that week/);
    expect(validateChoreReminderDate(evenWeek, '2021-01-11')).toBe('');
  });

  it('rejects invalid dates and permits alternating duties without a reference', () => {
    expect(validateChoreReminderDate({}, '2026-02-30')).toMatch(/valid day/);
    expect(nextChoreReminderDate({}, 'invalid')).toBeNull();
    expect(validateChoreReminderDate({ week_schedule: 'alternating' }, '2026-10-12')).toBe('');
  });

  it('uses the Phoenix calendar day near UTC midnight and includes only saved duty details', () => {
    const event = choreReminderEvent({ id: 9, title: 'Feed cat', description: 'After dinner' }, new Date('2026-10-12T02:00:00Z'));
    expect(event).toEqual({
      id: 'chore:9', title: 'Duty reminder: Feed cat', start: '2026-10-11',
      description: 'A one-day reminder for this duty.', path: '/quests?tab=duties',
    });
  });

  it('does not export inactive duties or proposals awaiting parent review', () => {
    expect(choreReminderEvent({ id: 1, is_active: false })).toBeNull();
    expect(choreReminderEvent({ id: 2, pending_parent_review: true })).toBeNull();
  });
});

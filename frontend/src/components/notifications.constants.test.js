import { describe, expect, it } from 'vitest';
import { NOTIFICATION_TYPE_META, destinationForNotification, metaForNotification } from './notifications.constants.js';

// Hand-maintained mirror of apps/notifications/models.py::NotificationType.
// If the backend adds a new value, add it here AND add a row to
// NOTIFICATION_TYPE_META — this test fails otherwise so the bell never
// silently degrades to the generic Bell + no-route fallback for a new type.
const BACKEND_NOTIFICATION_TYPES = [
  'timecard_ready', 'timecard_approved', 'badge_earned', 'project_approved',
  'project_changes', 'payout_recorded', 'skill_unlocked', 'milestone_completed',
  'redemption_requested', 'chore_submitted', 'chore_approved', 'chore_rejected',
  'exchange_requested', 'exchange_approved', 'exchange_denied',
  'project_due_soon', 'chore_reminder', 'approval_reminder',
  'homework_created', 'homework_submitted', 'homework_approved',
  'homework_rejected', 'homework_due_soon', 'streak_milestone', 'streak_at_risk',
  'perfect_day', 'daily_check_in', 'savings_goal_completed', 'birthday',
  'chronicle_first_ever', 'comeback_suggested', 'creation_submitted',
  'creation_approved', 'creation_rejected', 'chore_proposed',
  'habit_proposed', 'chore_proposal_approved', 'habit_proposal_approved',
  'chore_proposal_rejected', 'habit_proposal_rejected', 'quest_completed',
  'drop_received', 'pet_evolved', 'mount_bred', 'low_reward_stock',
  'reward_restocked', 'expedition_returned', 'print_request_submitted',
  'print_request_approved', 'print_request_rejected', 'print_started',
  'print_finished', 'print_failed', 'print_budget_low', 'journal_reply',
];

describe('notification type meta', () => {
  it('has an entry for every backend NotificationType', () => {
    const missing = BACKEND_NOTIFICATION_TYPES.filter(
      (t) => !NOTIFICATION_TYPE_META[t],
    );
    expect(missing).toEqual([]);
  });

  it('falls back to a generic icon and no route for unknown types', () => {
    const meta = metaForNotification({ notification_type: 'something_new' });
    expect(meta.Icon).toBeDefined();
    expect(meta.defaultRoute).toBeNull();
  });

  it('returns a route for badge_earned', () => {
    const meta = metaForNotification({ notification_type: 'badge_earned' });
    expect(meta.defaultRoute).toBe('/atlas?tab=badges');
  });

  it('returns to the journal for a family response', () => {
    expect(metaForNotification({ notification_type: 'journal_reply' }).defaultRoute)
      .toBe('/chronicle?tab=journal');
  });
});

describe('notification destinations across parent spaces', () => {
  it.each(['pet_evolved', 'expedition_returned'])('keeps an ambiguous historical %s out of the parent’s own pets', notification_type => {
    expect(destinationForNotification({ notification_type, link: '/bestiary?tab=mounts' }, { isParentAccount: true }))
      .toEqual({ space: 'family', target: '/family' });
  });

  it.each(['pet_evolved', 'expedition_returned'])('uses the explicit owner hint for a new personal %s', notification_type => {
    const link = '/bestiary?tab=mounts&space=personal';
    expect(destinationForNotification({ notification_type, link }, { isParentAccount: true }))
      .toEqual({ space: 'personal', target: link });
  });

  it('retains the exact child’s Family destination', () => {
    expect(destinationForNotification({ notification_type: 'pet_evolved', link: '/family?child=7' }, { isParentAccount: true }))
      .toEqual({ space: 'family', target: '/family?child=7' });
  });

  it.each(['pet_evolved', 'expedition_returned'])('preserves a child’s historical %s route', notification_type => {
    expect(destinationForNotification({ notification_type, link: '/bestiary?tab=mounts' }))
      .toEqual({ space: null, target: '/bestiary?tab=mounts' });
  });

  it.each([
    ['chore_submitted', '/bestiary?space=personal', 'family'],
    ['badge_earned', '/atlas?tab=badges', 'personal'],
  ])('preserves non-pet %s destinations', (notification_type, link, space) => {
    expect(destinationForNotification({ notification_type, link }, { isParentAccount: true })).toEqual({ space, target: link });
  });

  it.each([
    ['journal_reply', '/chronicle?tab=journal&space=personal', 'personal', '/chronicle?tab=journal&space=personal'],
    ['journal_reply', '/chronicle?tab=grades&child=7&space=family', 'family', '/chronicle?tab=grades&child=7&space=family'],
    ['journal_reply', '/chronicle?tab=journal', 'family', '/family'],
    ['savings_goal_completed', '', 'family', '/family'],
    ['savings_goal_completed', '/treasury?tab=hoards', 'personal', '/treasury?tab=hoards'],
    ['savings_goal_completed', '/treasury?tab=hoards&space=personal', 'personal', '/treasury?tab=hoards&space=personal'],
    ['chore_approved', '/chores?space=personal', 'personal', '/chores?space=personal'],
    ['chore_approved', '/chores', 'personal', '/chores'],
    ['chore_approved', '', 'personal', '/quests?tab=duties'],
    ['project_approved', '/projects/123?space=personal', 'personal', '/projects/123?space=personal'],
  ])('routes known parent %s audiences from %s', (notification_type, link, space, target) => {
    expect(destinationForNotification({ notification_type, link }, { isParentAccount: true })).toEqual({ space, target });
  });

  it('keeps legacy project approval notifications in their current space', () => {
    expect(destinationForNotification({ notification_type: 'project_approved', link: '/projects/123' }, { isParentAccount: true }))
      .toEqual({ space: null, target: '/projects/123' });
  });

  it.each([
    'https://outside.example/bestiary?space=personal', '//outside.example/bestiary?space=personal',
    '/quests?space=personal', '/bestiary?space=personal&space=family',
  ])('does not accept a personal pet hint on an ambiguous or unrelated link: %s', link => {
    expect(destinationForNotification({ notification_type: 'pet_evolved', link }, { isParentAccount: true }))
      .toEqual({ space: 'family', target: '/family' });
  });
});

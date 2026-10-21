// Local synthetic examples: no account identity, request token or live API data.
const WEEK_START = '2026-10-12T07:00:00Z';
const WEEK_END = '2026-10-19T07:00:00Z';

function goal(id, name, overrides = {}) {
  return {
    id: `goal:${id}`,
    name,
    description: 'A small goal for the week. Matching saved work counts automatically.',
    origin: 'catalog',
    metric: 'count',
    target: '10',
    progress: '0',
    unit: 'actions',
    status: 'active',
    starts_at: WEEK_START,
    ends_at: WEEK_END,
    timezone: 'America/Phoenix',
    what_counts: 'Matching saved activities during this period.',
    rewards: { coins: 10, xp: 20, items: [] },
    reward_receipt: { status: 'pending', coins_awarded: 0, xp_awarded: 0, awarded_at: null },
    action: null,
    pinned: false,
    repeat_weekly: false,
    legacy: false,
    ...overrides,
  };
}

export const TASKS_SHOWCASE_TIMEZONE = 'America/Phoenix';
export const TASKS_SHOWCASE_PIN = 'goal:101';
export const TASKS_SHOWCASE_GOALS = [
  goal(101, 'Run 2 miles this week', {
    origin: 'parent',
    description: 'A goal from your parent: make room for a few short runs this week.',
    metric: 'distance',
    target: '2',
    progress: '1.25',
    unit: 'mi',
    what_counts: 'Logged Running distance. Every valid running session this week counts.',
    pinned: true,
    repeat_weekly: true,
    rewards: { coins: 15, xp: 30, items: [] },
  }),
  goal(102, 'Practice piano for 60 minutes', {
    origin: 'parent',
    metric: 'minutes',
    target: '60',
    progress: '20',
    unit: 'minutes',
    what_counts: 'Saved minutes on your piano project during this week.',
  }),
  goal(103, 'Keep moving', {
    qualifying_triggers: ['movement_session'],
    metric: 'minutes', target: '50', progress: '30', unit: 'minutes',
    what_counts: 'Minutes from valid logged movement sessions.',
  }),
  goal(104, 'Homework rhythm', {
    qualifying_triggers: ['homework_complete'],
    target: '5', progress: '2',
    what_counts: 'Approved homework during this period.',
  }),
  goal(105, 'Creative practice', {
    qualifying_triggers: ['creation_logged'],
    target: '8', progress: '2',
    what_counts: 'The first two logged creations each day during this period.',
  }),
  goal(106, 'Focus time', {
    qualifying_triggers: ['clock_out'],
    metric: 'minutes', target: '100', progress: '10', unit: 'minutes',
    what_counts: 'Saved project work minutes during this period.',
  }),
  goal(107, 'Build momentum', {
    qualifying_triggers: ['milestone_complete'],
    what_counts: 'Completed project milestones during this period.',
  }),
  goal(108, 'Read together next week', {
    origin: 'parent',
    target: '3',
    status: 'upcoming',
    starts_at: WEEK_END,
    ends_at: '2026-10-26T07:00:00Z',
    what_counts: 'Approved reading homework next week.',
  }),
  goal(109, 'A week of practice', {
    progress: '10',
    status: 'completed',
    starts_at: '2026-10-05T07:00:00Z',
    ends_at: WEEK_START,
    reward_receipt: {
      status: 'awarded', coins_awarded: 10, xp_awarded: 20,
      awarded_at: '2026-10-11T19:00:00Z', items: [],
    },
  }),
  goal(110, 'Earlier challenge', {
    id: 'legacy:110',
    origin: 'legacy',
    legacy: true,
    status: 'expired',
    progress: '3',
    starts_at: '2026-10-05T07:00:00Z',
    ends_at: WEEK_START,
    reward_receipt: { status: 'legacy', coins_awarded: 0, xp_awarded: 0, awarded_at: null },
  }),
];

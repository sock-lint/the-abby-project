export function buildChallengeGoal(overrides = {}) {
  return {
    id: 'goal:11', name: 'Run 2 miles this week', description: 'Make time to move.',
    metric: 'distance', progress: '0.75', target: '2.00', unit: 'mi', status: 'active',
    starts_at: '2026-10-12T07:00:00Z', ends_at: '2026-10-19T07:00:00Z',
    what_counts: 'Running sessions logged after this goal was created. Distances add together.',
    rewards: { coins: 10, xp: 0, items: [] }, pinned: false, repeat_weekly: false, legacy: false,
    reward_receipt: { status: overrides.status === 'completed' ? 'awarded' : 'pending', coins_awarded: 10, xp_awarded: 0 },
    action: { label: 'Log a run', path: '/quests?tab=movement', movement_type_id: 3 },
    ...overrides,
  };
}

export function buildDailyBonus(overrides = {}) {
  return {
    date: '2026-10-13', timezone: 'America/Phoenix',
    goal: 'Complete an approved task or log 10 minutes of work or movement',
    progress_minutes: 4, completed: false, awarded: false,
    coin_reward: 10, xp_reward: 20, coins_awarded: 0, xp_awarded: 0,
    ends_at: '2026-10-14T07:00:00Z', receipt_id: null,
    ...overrides,
  };
}

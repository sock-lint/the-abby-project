/** An empty, well-shaped heartbeat — the same shape /api/pulse/ returns. */
export function emptyPulse(overrides = {}) {
  return {
    unread_count: 0,
    notifications: [],
    recent_drops: [],
    active_quest: null,
    companion_growth: { events: [] },
    expeditions_ready: [],
    savings_goals: [],
    newly_unlocked_lorebook: [],
    header: { active_timer: null, coin_balance: 0, streak_days: 0 },
    ...overrides,
  };
}

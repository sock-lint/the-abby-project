export const gateDefaults = { mode: 'current', start_date: '2026-01-01', rules: [] };
export const gateRule = { quest_id: 11, prerequisite_quest_id: 10, skill_id: 7, skill_level: 2, min_days: 14, available_from: '2026-01-05', available_until: '2026-02-01' };
export const gateMetadata = {
  challenge_gates_defaults: gateDefaults,
  challenge_gates_limits: { max_rules: 20 },
  challenge_gate_choices: {
    quests: [{ id: 10, name: 'First pages', is_repeatable: false }, { id: 11, name: 'Next chapter', is_repeatable: false }, { id: 12, name: 'Reading week', is_repeatable: true }],
    skills: [{ id: 7, name: 'Reading', category: 'Knowledge' }],
  },
};
export const gateReport = {
  mode: 'milestone_tenure', config: { ...gateDefaults, mode: 'milestone_tenure', rules: [gateRule] },
  scope: 'One-time challenges compatible with this routine.', trials: 3,
  native_finite_total: 12, gate_reachable_finite_total: 11, gate_unreachable_finite_total: 1,
  visits: { active_visits_p50: 22, with_available_challenge_p50: 10, without_available_challenge_p50: 12, waiting_for_gate_p50: 7, exhausted_or_expired_p50: 5 },
  targets: [{ quest_id: 11, name: 'Next chapter', in_native_subset: true, reachable: true, unreachable_reasons: [], unlocked_trials: 2, completed_trials: 1, p10_unlock_days: 15, p50_unlock_days: 15, p90_unlock_days: 15, p10_completion_days: 19, p50_completion_days: 19, p90_completion_days: 19, temporarily_locked_trials: 1, blocked_trials: 0, blocked_reasons: [], expired_trials: 1 },
    { quest_id: 10, name: 'First pages', in_native_subset: true, reachable: false, unreachable_reasons: ['availability_closed'], unlocked_trials: 0, completed_trials: 0, p50_unlock_days: null, p50_completion_days: null, temporarily_locked_trials: 0, blocked_trials: 0, blocked_reasons: [], expired_trials: 3 },
    { quest_id: 13, name: 'Later chapter', in_native_subset: true, reachable: true, unreachable_reasons: [], unlocked_trials: 0, completed_trials: 0, p50_unlock_days: null, p50_completion_days: null, temporarily_locked_trials: 0, blocked_trials: 3, blocked_reasons: ['prerequisite_window_expired'], expired_trials: 0 }],
  assumptions: ['Existing badge prerequisites remain required.'],
};

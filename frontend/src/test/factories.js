// Minimal fixture builders. Keep them tiny — tests should be self-describing,
// so only centralize shapes that many tests share verbatim.

export function buildUser(over = {}) {
  return {
    id: 1,
    username: 'abby',
    role: 'child',
    first_name: 'Abby',
    hourly_rate: '10.00',
    theme: 'hyrule',
    ...over,
  };
}

export function buildParent(over = {}) {
  return buildUser({ id: 99, username: 'parent', role: 'parent', ...over });
}

export function buildProject(over = {}) {
  return {
    id: 1,
    title: 'Build a Bird Feeder',
    description: 'A wooden feeder for the backyard.',
    status: 'active',
    payment_kind: 'required',
    difficulty: 3,
    reward_amount: '15.00',
    hourly_rate_override: null,
    assigned_to: buildUser(),
    category: null,
    milestones: [],
    steps: [],
    materials: [],
    resources: [],
    ...over,
  };
}

export function buildBadge(over = {}) {
  return {
    id: 1,
    name: 'First Project',
    description: 'You finished your first project!',
    icon: 'award',
    rarity: 'common',
    criterion_type: 'projects_completed',
    criterion_value: 1,
    ...over,
  };
}

export function buildChore(over = {}) {
  return {
    id: 1,
    title: 'Dishes',
    icon: 'utensils',
    reward_amount: '1.00',
    coin_reward: 5,
    recurrence: 'daily',
    week_schedule: 'every_week',
    is_active_this_week: true,
    ...over,
  };
}

export function buildNotification(over = {}) {
  return {
    id: 1,
    notification_type: 'redemption_requested',
    message: 'Abby redeemed a reward',
    is_read: false,
    created_at: '2026-04-16T12:00:00Z',
    ...over,
  };
}

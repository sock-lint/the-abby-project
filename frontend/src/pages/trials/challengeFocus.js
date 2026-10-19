const BONUS_PREVIEW_LIMIT = 3;

function progressRatio(goal) {
  const target = Number(goal.target);
  const progress = Number(goal.progress);
  return target > 0 && Number.isFinite(progress) ? Math.min(1, Math.max(0, progress / target)) : 0;
}

// Presentation only: the complete server response stays available to details
// and pinning. Selecting a preview never changes which activities count.
export function challengeFocus(goals, pinnedGoal) {
  const pinned = goals.find((goal) => goal.id === pinnedGoal?.id && goal.status === 'active') || null;
  const active = goals.filter((goal) => goal.status === 'active' && goal.id !== pinned?.id);
  const parentGoals = active.filter((goal) => goal.origin === 'parent');
  const upcoming = goals.filter((goal) => goal.status === 'upcoming' && goal.id !== pinned?.id);
  const bonusGoals = active.filter((goal) => goal.origin !== 'parent');
  const explore = bonusGoals.filter((goal) => goal.origin === 'catalog' && goal.catalog_repeatable === false && !goal.first_details_opened_at)
    .sort((a, b) => (Date.parse(b.starts_at) || 0) - (Date.parse(a.starts_at) || 0) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
    .slice(0, BONUS_PREVIEW_LIMIT);
  const exploreIds = new Set(explore.map((goal) => goal.id));
  const bonusPreview = bonusGoals.filter((goal) => !exploreIds.has(goal.id) && progressRatio(goal) > 0)
    .sort((a, b) => progressRatio(b) - progressRatio(a) || a.name.localeCompare(b.name) || a.id.localeCompare(b.id))
    .slice(0, BONUS_PREVIEW_LIMIT);
  const previewIds = new Set([...explore, ...bonusPreview].map((goal) => goal.id));
  return {
    pinned, parentGoals, upcoming, explore, bonusPreview,
    otherBonuses: bonusGoals.filter((goal) => !previewIds.has(goal.id)),
    history: goals.filter((goal) => !['active', 'upcoming'].includes(goal.status)),
    parentCount: goals.filter((goal) => goal.origin === 'parent' && ['active', 'upcoming'].includes(goal.status)).length,
    pinnedProgress: pinned ? progressRatio(pinned) * 100 : 0,
  };
}

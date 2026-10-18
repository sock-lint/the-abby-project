import useParentDashboard from './useParentDashboard';

// Header, navigation and Today read one shared aggregation. Standalone
// consumers retain the same complete loader for component tests/previews.
export default function useParentPendingCounts({ enabled = true } = {}) {
  const review = useParentDashboard({ enabled });
  if (!enabled) return { chores: 0, homework: 0, redemptions: 0, total: 0, ready: true, incomplete: false };
  const count = (kind) => review.pending.filter((row) => row.kind === kind).length;
  return {
    chores: count('chore'), homework: count('homework'), redemptions: count('redemption'),
    total: review.attentionCount, ready: !review.loading,
    incomplete: Boolean(review.error || review.failedSources.length),
  };
}

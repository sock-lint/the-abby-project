import { useCallback, useEffect } from 'react';
import { getChallenges } from '../api';
import { useApi } from './useApi';
import { useRole } from './useRole';
import { usePulse } from '../providers/pulseContext';
import { getToken } from '../api/client';
import { useSpace } from './useSpace';

export const CHALLENGES_CHANGED = 'abby:challenges-changed';

export default function useChallenges({ userId, refreshKey } = {}) {
  const { user } = useRole();
  const { isFamilySpace: isParent, space } = useSpace();
  const { pulse } = usePulse();
  const scope = `${user?.id}:${getToken()}:${space}:${userId || 'self'}`;
  const fetch = useCallback(async () => ({
    ...(user && (!isParent || userId) ? await getChallenges(userId) : { results: [], pin: null, daily_bonus: null }),
    _challengeScope: scope,
  }), [user, isParent, userId, scope]);
  const result = useApi(fetch, [scope, isParent, refreshKey, pulse]);
  const reload = result.reload;
  useEffect(() => {
    const update = () => reload();
    window.addEventListener(CHALLENGES_CHANGED, update);
    return () => window.removeEventListener(CHALLENGES_CHANGED, update);
  }, [reload]);
  const data = result.data?._challengeScope === scope ? result.data : null;
  const goals = data?.results || [];
  const setData = (update) => result.setData((previous) => previous?._challengeScope !== scope ? previous : {
    ...(typeof update === 'function' ? update(previous) : update), _challengeScope: scope,
  });
  return { ...result, data, setData, loading: result.loading || (!data && !result.error), goals, pinnedGoal: goals.find((goal) => goal.id === data?.pin && goal.status === 'active') || null };
}

import { useEffect, useRef } from 'react';
import { recordChallengeOpening } from '../api';
import { getToken } from '../api/client';

// Call only from mounted live details. Cards and design previews do not record
// an opening, and this receipt never claims the description was read.
export default function useChallengeOpening(goal, { user, onConfirmed, personal = false }) {
  const token = getToken();
  const goalId = goal?.id;
  const eligible = Boolean(token && user?.id && (user.role === 'child' || (user.role === 'parent' && personal))
    && typeof goalId === 'string' && goalId.startsWith('goal:')
    && goal.origin === 'catalog' && !goal.legacy && typeof goal.catalog_repeatable === 'boolean'
    && ['active', 'completed', 'expired'].includes(goal.status) && !goal.first_details_opened_at);
  const identity = `${user?.id}:${user?.role}:${user?.family?.id ?? ''}:${personal}:${token}:${goalId}`;
  const attempt = useRef(null);
  const confirmed = useRef(onConfirmed);
  useEffect(() => { confirmed.current = onConfirmed; }, [onConfirmed]);

  useEffect(() => {
    if (!eligible) return undefined;
    let mounted = true;
    // StrictMode replays effects for the same mounted details. Keep its one
    // promise, including a failure; closing/reopening starts a new attempt.
    if (attempt.current?.identity !== identity) {
      attempt.current = { identity, promise: recordChallengeOpening(goalId, { token }) };
    }
    attempt.current.promise.then((response) => {
      if (!mounted || getToken() !== token || response?.id !== goalId
        || typeof response.first_details_opened_at !== 'string'
        || !Number.isFinite(Date.parse(response.first_details_opened_at))) return;
      confirmed.current?.(response);
    }).catch(() => {
      // A failed receipt leaves the details readable and unconfirmed. Never
      // replay a possible write or interrupt the child's reading with analytics.
    });
    return () => { mounted = false; };
  }, [eligible, goalId, identity, token]);
}

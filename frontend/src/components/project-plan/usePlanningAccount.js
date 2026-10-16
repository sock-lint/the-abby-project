import { useMemo, useSyncExternalStore } from 'react';
import { useAuth } from '../../hooks/useApi';
import { AUTH_CHANGED_EVENT, getToken } from '../../api/client';

let nextGeneration = 0;

function subscribe(onChange) {
  window.addEventListener(AUTH_CHANGED_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

export function usePlanningAccount() {
  const { user } = useAuth();
  const token = useSyncExternalStore(subscribe, getToken, getToken);
  const generation = useMemo(() => token ? ++nextGeneration : 'anonymous', [token]);
  return { user, token, accountKey: `${user?.id}:${user?.family?.id ?? ''}:${generation}` };
}

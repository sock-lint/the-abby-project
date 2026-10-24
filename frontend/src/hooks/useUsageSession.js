import { useSyncExternalStore } from 'react';
import { AUTH_CHANGED_EVENT, getToken } from '../api/client';
import { useAuth } from './useApi';

function subscribe(onChange) {
  window.addEventListener(AUTH_CHANGED_EVENT, onChange);
  window.addEventListener('storage', onChange);
  return () => {
    window.removeEventListener(AUTH_CHANGED_EVENT, onChange);
    window.removeEventListener('storage', onChange);
  };
}

// The key is component state only; credentials never enter markup or telemetry.
export default function useUsageSession() {
  const { user } = useAuth();
  const token = useSyncExternalStore(subscribe, getToken, getToken);
  return { user, token, key: `${user?.id}:${user?.family?.id ?? ''}:${user?.role}:${user?.is_staff}:${token}` };
}

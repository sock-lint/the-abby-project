import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { recordUsageVisit } from '../api';
import { getToken } from '../api/client';
import useUsageSession from '../hooks/useUsageSession';

// Bounded, memory-only deduplication survives StrictMode effect replay and route
// remounts. Mark before sending: an uncertain POST must never be replayed.
const attempts = new Map();

export default function UsageVisitCapture() {
  const { user, token, key } = useUsageSession();
  const { pathname } = useLocation();
  const userId = user?.id;
  const collectionEnabled = user?.usage_collection_enabled !== false;
  useEffect(() => {
    const capture = () => {
      if (!collectionEnabled || !userId || !token || token !== getToken() || document.visibilityState !== 'visible') return;
      if (['/login', '/signup', '/__design'].includes(pathname)) return;
      const day = new Date().toISOString().slice(0, 10);
      if (attempts.get(key) === day) return;
      attempts.set(key, day);
      if (attempts.size > 16) attempts.delete(attempts.keys().next().value);
      // No page path, query, text, content, duration or replay is collected.
      void recordUsageVisit({ token, selfHeal: false }).catch(() => {});
    };
    capture();
    document.addEventListener('visibilitychange', capture);
    return () => document.removeEventListener('visibilitychange', capture);
  }, [collectionEnabled, key, pathname, token, userId]);
  return null;
}

import { useEffect, useRef } from 'react';
import { useAuth } from '../hooks/useApi';
import { getToken } from '../api/client';
import { PARENT_REVIEW_CHANGED } from '../api/parentReviewRefresh';
import { useParentDashboardData } from '../hooks/useParentDashboard';
import { usePulse } from './pulseContext';
import { ParentReviewContext } from './parentReviewContext';

export default function ParentReviewProvider({ children }) {
  const { user } = useAuth();
  const enabled = user?.role === 'parent';
  const accountScope = `${user?.id}:${user?.role}:${user?.family?.id}:${getToken()}`;
  const review = useParentDashboardData({ enabled, accountScope });
  const { reload } = review;
  const { pulse } = usePulse();
  const signature = pulse?.parent_attention?.revision ?? JSON.stringify(pulse?.parent_attention?.counts ?? null);
  const lastSignature = useRef(null);

  useEffect(() => {
    if (!enabled) { lastSignature.current = null; return; }
    if (signature === 'null') return;
    if (lastSignature.current !== signature) void reload();
    lastSignature.current = signature;
  }, [enabled, signature, reload]);

  useEffect(() => {
    if (!enabled) return undefined;
    let timer;
    const changed = (event) => {
      if (event?.detail && event.detail.token !== getToken()) return;
      clearTimeout(timer);
      timer = setTimeout(() => { void reload(); }, 60);
    };
    const visible = () => { if (!document.hidden) changed(); };
    window.addEventListener(PARENT_REVIEW_CHANGED, changed);
    document.addEventListener('visibilitychange', visible);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(PARENT_REVIEW_CHANGED, changed);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [enabled, reload]);

  return <ParentReviewContext.Provider value={review}>{children}</ParentReviewContext.Provider>;
}

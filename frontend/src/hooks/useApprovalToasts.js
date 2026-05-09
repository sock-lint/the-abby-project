import { useState, useEffect, useRef } from 'react';
import { getNotifications } from '../api';
import { STORAGE_KEYS } from '../constants/storage';
import { useAuth } from './useApi';

const STORAGE_KEY = STORAGE_KEYS.SEEN_APPROVAL_TOASTS;
const POLL_INTERVAL_MS = 30000;

// Notification types where the *child* receives the row when a parent
// has decided on their submission. Approval-style decisions only —
// reminders / parent-side queue notifications are not in this set.
const APPROVAL_TYPES = new Set([
  'chore_approved',
  'chore_rejected',
  'homework_approved',
  'homework_rejected',
  'creation_approved',
  'creation_rejected',
  'exchange_approved',
  'exchange_denied',
  'chore_proposal_approved',
  'chore_proposal_rejected',
  'habit_proposal_approved',
  'habit_proposal_rejected',
]);

const POSITIVE_TYPES = new Set([
  'chore_approved',
  'homework_approved',
  'creation_approved',
  'exchange_approved',
  'chore_proposal_approved',
  'habit_proposal_approved',
]);

function loadSeen() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

function persistSeen(set) {
  try {
    // Cap at the most recent 200 IDs so the key doesn't grow forever
    // for long-tenured kids — older notifications won't re-toast either
    // way because they'll be marked is_read=true on the bell click.
    const trimmed = [...set].slice(-200);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Quota / privacy mode — silent fail; we'd just re-toast once per
    // session in the worst case.
  }
}

/**
 * Polls the child's notifications for newly-arrived approval decisions
 * (chore approved, homework approved, creation approved, etc.) and
 * emits a toast the first time we observe each one.
 *
 * Independent from `is_read` on the notification: a child can dismiss
 * the toast and still see the row in the bell. Seen IDs persist in
 * localStorage so a refresh doesn't re-toast.
 *
 * Parents never see these — child-only by role gate.
 *
 * Returns `{ toasts, dismiss }` — same contract as `useDropToasts` and
 * `useSavingsCompletionToasts`. Toast shape:
 *   { id, title, message, type, positive }
 */
export function useApprovalToasts(pollIntervalMs = POLL_INTERVAL_MS) {
  const { user } = useAuth();
  const [toasts, setToasts] = useState([]);
  const seenRef = useRef(loadSeen());
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!user || user.role !== 'child') return undefined;
    let cancelled = false;

    const poll = async () => {
      // Skip backgrounded tab — same-rationale as useDropToasts.
      if (typeof document !== 'undefined' && document.hidden) return;
      try {
        const data = await getNotifications();
        const list = Array.isArray(data)
          ? data
          : (data?.results || []);
        if (cancelled) return;

        const approvalRows = list.filter(
          (n) => APPROVAL_TYPES.has(n.notification_type),
        );

        if (!initializedRef.current) {
          // Seed seen IDs without toasting — first poll catches up to
          // whatever already happened pre-mount.
          for (const n of approvalRows) seenRef.current.add(n.id);
          persistSeen(seenRef.current);
          initializedRef.current = true;
          return;
        }

        const fresh = approvalRows.filter((n) => !seenRef.current.has(n.id));
        if (fresh.length === 0) return;

        for (const n of fresh) seenRef.current.add(n.id);
        persistSeen(seenRef.current);

        setToasts((prev) => [
          ...prev,
          ...fresh.map((n) => ({
            id: n.id,
            title: n.title,
            message: n.message,
            type: n.notification_type,
            positive: POSITIVE_TYPES.has(n.notification_type),
          })),
        ]);
      } catch {
        // silent — caught on next poll
      }
    };

    poll();
    const interval = setInterval(poll, pollIntervalMs);
    const onVisibility = () => {
      if (typeof document !== 'undefined' && !document.hidden) poll();
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibility);
    }
    return () => {
      cancelled = true;
      clearInterval(interval);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisibility);
      }
    };
  }, [pollIntervalMs, user]);

  const dismiss = (id) => setToasts((prev) => prev.filter((t) => t.id !== id));

  return { toasts, dismiss };
}

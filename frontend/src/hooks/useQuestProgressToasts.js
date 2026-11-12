import { useEffect, useRef, useState } from 'react';
import { usePulse } from '../providers/pulseContext';
import { useAuth } from './useApi';
import { useSpaceForUser } from './useSpace';

export function useQuestProgressToasts() {
  const { user } = useAuth();
  const { isPersonalSpace } = useSpaceForUser(user);
  const { pulse } = usePulse();
  const [toasts, setToasts] = useState([]);
  const seenRef = useRef({ account: null, ids: new Set() });

  useEffect(() => {
    const account = user?.id && isPersonalSpace ? String(user.id) : null;
    if (seenRef.current.account !== account) {
      let ids = [];
      try { ids = JSON.parse(localStorage.getItem(`abby:challenge-receipts:${account}`) || '[]'); } catch { /* storage may be unavailable */ }
      seenRef.current = { account, ids: new Set(Array.isArray(ids) ? ids : []) };
      // eslint-disable-next-line react-hooks/set-state-in-effect -- receipts belong to the authenticated participant
      setToasts([]);
    }
    if (!account || !pulse) return;
    const receipts = (pulse.challenge_receipts || []).filter((receipt) => receipt?.id && !seenRef.current.ids.has(receipt.id));
    if (!receipts.length) return;
    for (const receipt of receipts) seenRef.current.ids.add(receipt.id);
    const savedIds = [...seenRef.current.ids].slice(-200);
    seenRef.current.ids = new Set(savedIds);
    try { localStorage.setItem(`abby:challenge-receipts:${account}`, JSON.stringify(savedIds)); } catch { /* dedupe still works in this session */ }
    // Reads return newest first. Append oldest first so the bounded stack
    // keeps the newest completions rather than dropping them as already seen.
    const visible = receipts.filter((receipt) => receipt.goals?.length || receipt.daily_bonus?.awarded).reverse();
    setToasts((previous) => [...previous, ...visible].slice(-3));
  }, [pulse, user, isPersonalSpace]);

  const dismiss = (id) => setToasts((previous) => previous.filter((receipt) => receipt.id !== id));
  return { toasts, dismiss };
}

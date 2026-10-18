import { useRef, useState } from 'react';
import { getToken } from '../api/client';
import useMountedRef from './useMountedRef';
import { getTodayJournal } from '../api';
import { useApi } from './useApi';

/** Shared read-before-write state for every daily journal entry point. */
export default function useJournalCapture(enabled = true) {
  const today = useApi(enabled ? getTodayJournal : () => Promise.resolve(null), [enabled]);
  const mounted = useMountedRef();
  const opening = useRef(false);
  const [capture, setCapture] = useState(null);
  const open = async () => {
    // A failed or unfinished lookup does not establish that no entry exists.
    if (!enabled || today.loading || today.refreshing || today.error || opening.current) return;
    opening.current = true;
    const token = getToken();
    try {
      // Another entry point or tab may have saved since the page loaded.
      // Refresh before capture, including after local midnight.
      const entry = await today.reload();
      if (!mounted.current || getToken() !== token || entry === undefined) return;
      setCapture(entry?.id ? { mode: 'edit', entry } : { mode: 'create', entry: null });
    } finally {
      opening.current = false;
    }
  };
  const saved = (entry) => {
    setCapture(null);
    if (entry?.id) today.setData(entry);
  };
  return { ...today, capture, open, close: () => setCapture(null), saved };
}

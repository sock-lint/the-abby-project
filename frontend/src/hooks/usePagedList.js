import { useCallback, useEffect, useRef, useState } from 'react';
import { normalizeList } from '../utils/api';
import { friendlyErrorMessage } from './useApi';

const empty = { items: [], count: 0, nextPage: null, pages: 0, loading: true, refreshing: false, loadingMore: false, error: null, moreError: null };

// fetchPage must be stable and bound to the current account/filters. Follow
// DRF's page numbers through that known endpoint, never a server-provided URL.
export default function usePagedList(fetchPage) {
  const [state, setState] = useState(empty);
  const snapshot = useRef(null);
  const generation = useRef(0);
  const pending = useRef(null);

  const publish = useCallback((value) => {
    snapshot.current = value;
    setState(value);
  }, []);

  const load = useCallback(async (more = false) => {
    const previous = snapshot.current?.source === fetchPage ? snapshot.current : empty;
    if (more && (!previous.nextPage || pending.current)) return;
    const version = more ? generation.current : ++generation.current;
    const ticket = Symbol('list request');
    pending.current = ticket;
    publish({ ...previous, source: fetchPage, loading: previous.pages === 0, refreshing: !more && previous.pages > 0, loadingMore: more, error: null, moreError: null });
    try {
      const items = new Map((more ? previous.items : []).map((item) => [item.id, item]));
      const lastPage = more ? previous.nextPage : Math.max(1, previous.pages);
      let count = 0;
      let nextPage = null;
      let page = more ? previous.nextPage : 1;
      for (; page <= lastPage; page += 1) {
        const response = await fetchPage(page);
        if (generation.current !== version) return;
        for (const item of normalizeList(response)) items.set(item.id, item);
        count = response?.count ?? items.size;
        nextPage = response?.next ? page + 1 : null;
        if (!nextPage) break;
      }
      const value = { source: fetchPage, items: [...items.values()], count, nextPage, pages: Math.min(page, lastPage), loading: false, refreshing: false, loadingMore: false, error: null, moreError: null };
      publish(value);
      return value;
    } catch (error) {
      if (generation.current !== version) return;
      publish({ ...previous, source: fetchPage, loading: false, refreshing: false, loadingMore: false, [more ? 'moreError' : 'error']: friendlyErrorMessage(error) });
    } finally {
      if (pending.current === ticket) pending.current = null;
    }
  }, [fetchPage, publish]);

  useEffect(() => {
    void load();
    return () => { generation.current += 1; pending.current = null; };
  }, [load]);

  // A changed filter must never render records from the previous request,
  // even for the render before its effect starts.
  const visible = state.source === fetchPage ? state : empty;
  const reload = useCallback(() => load(), [load]);
  const loadMore = useCallback(() => load(true), [load]);
  return { ...visible, reload, loadMore };
}

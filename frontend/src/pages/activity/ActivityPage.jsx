import { useMemo, useState } from 'react';
import { History } from 'lucide-react';
import { listActivity, fetchActivityUrl, getChildren } from '../../api';
import { useApi } from '../../hooks/useApi';
import Loader from '../../components/Loader';
import EmptyState from '../../components/EmptyState';
import ErrorAlert from '../../components/ErrorAlert';
import Button from '../../components/Button';
import { normalizeList } from '../../utils/api';
import EventRow from './EventRow';
import {
  CATEGORY_META, CATEGORY_ORDER, dayKey, formatDayHeader,
} from './activity.constants';

/**
 * Parent-only activity log page.
 *
 * Reads ``/api/activity/`` with optional ``subject`` / ``category`` filters
 * and walks the cursor-paginated response via the ``next`` URL. Rows group
 * by day. Every ActivityEvent renders through the generic ``<EventRow>``
 * regardless of ``event_type`` — see ``activity.constants.js`` for the
 * category → icon/color mapping.
 */
export default function ActivityPage() {
  const [subject, setSubject] = useState('');
  const [category, setCategory] = useState('');

  // Initial fetch + re-fetch when filters change goes through the shared
  // ``useApi`` hook — that hook owns the AbortController + unmount-guard
  // + initial-setState-in-effect pattern, so callers don't repeat it.
  const { data, loading, error } = useApi(
    () => listActivity({ subject, category }),
    [subject, category],
  );

  // Paginated extras. ``data`` is the first page; additional pages land
  // in ``extras`` via the "Load older" button — never in an effect.
  const [extras, setExtras] = useState([]);
  const [nextUrlOverride, setNextUrlOverride] = useState(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(null);

  // Reset pagination state inline when filters change (keeps setState out
  // of an effect body — ``useApi`` already handles the refetch on dep change).
  const changeSubject = (value) => {
    setSubject(value);
    setExtras([]);
    setNextUrlOverride(null);
    setLoadMoreError(null);
  };
  const changeCategory = (value) => {
    setCategory(value);
    setExtras([]);
    setNextUrlOverride(null);
    setLoadMoreError(null);
  };

  // Children list for the filter dropdown. Never blocks the main view.
  const { data: childrenData } = useApi(getChildren, []);
  const children = normalizeList(childrenData);

  const nextUrl = nextUrlOverride !== null ? nextUrlOverride : data?.next || null;
  const events = useMemo(
    () => [...(data?.results || []), ...extras],
    [data, extras],
  );

  const handleLoadMore = () => {
    if (!nextUrl || loadingMore) return;
    setLoadingMore(true);
    setLoadMoreError(null);
    fetchActivityUrl(nextUrl)
      .then((page) => {
        setExtras((prev) => [...prev, ...(page.results || [])]);
        setNextUrlOverride(page.next || null);
      })
      .catch((err) => setLoadMoreError(err.message || 'Failed to load more.'))
      .finally(() => setLoadingMore(false));
  };

  const groups = useMemo(() => {
    const grouped = events.reduce((acc, event) => {
      const key = dayKey(event.occurred_at);
      if (!acc[key]) acc[key] = { key, iso: event.occurred_at, events: [] };
      acc[key].events.push(event);
      return acc;
    }, {});
    return Object.values(grouped);
  }, [events]);

  return (
    <div className="space-y-6">
      <header className="flex items-center gap-3">
        <History
          size={24} className="text-sheikah-teal-deep" aria-hidden="true"
        />
        <div>
          <h1 className="font-display text-2xl text-ink-primary">
            Activity Log
          </h1>
          <p className="text-caption text-ink-secondary">
            Every interaction and calculation across your children, newest first.
          </p>
        </div>
      </header>

      <section aria-label="Filters" className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor="activity-subject"
            className="text-caption text-ink-secondary"
          >
            Child
          </label>
          <select
            id="activity-subject"
            value={subject}
            onChange={(e) => changeSubject(e.target.value)}
            className="rounded-md border border-ink-page-shadow bg-ink-page-aged px-2 py-1 text-body text-ink-primary"
          >
            <option value="">All children</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name || c.username}
              </option>
            ))}
          </select>
        </div>

        <div
          role="tablist" aria-label="Category filters"
          className="flex flex-wrap gap-1"
        >
          <button
            type="button"
            role="tab"
            aria-selected={category === ''}
            onClick={() => changeCategory('')}
            className={`px-2 py-1 rounded-md text-caption border ${
              category === ''
                ? 'bg-sheikah-teal/15 border-sheikah-teal-deep text-ink-primary'
                : 'border-ink-page-shadow text-ink-secondary hover:text-ink-primary'
            }`}
          >
            All
          </button>
          {CATEGORY_ORDER.map((key) => {
            const meta = CATEGORY_META[key];
            const selected = category === key;
            return (
              <button
                type="button"
                key={key}
                role="tab"
                aria-selected={selected}
                onClick={() => changeCategory(key)}
                className={`px-2 py-1 rounded-md text-caption border ${
                  selected
                    ? 'bg-sheikah-teal/15 border-sheikah-teal-deep text-ink-primary'
                    : 'border-ink-page-shadow text-ink-secondary hover:text-ink-primary'
                }`}
              >
                {meta.label}
              </button>
            );
          })}
        </div>
      </section>

      {error && <ErrorAlert>{error}</ErrorAlert>}
      {loadMoreError && <ErrorAlert>{loadMoreError}</ErrorAlert>}
      {loading && <Loader label="Loading activity…" />}

      {!loading && !error && events.length === 0 && (
        <EmptyState>
          No activity yet. Once your children clock in, submit chores, or
          claim rewards, a live log will appear here.
        </EmptyState>
      )}

      {!loading && groups.map((group) => (
        <section key={group.key} aria-label={`Events on ${group.key}`}>
          <h2 className="font-display text-lede text-ink-primary mb-2">
            {formatDayHeader(group.iso)}
          </h2>
          <ul className="space-y-2">
            {group.events.map((event) => (
              <li key={event.id}>
                <EventRow event={event} />
              </li>
            ))}
          </ul>
        </section>
      ))}

      {nextUrl && !loading && (
        <div className="flex justify-center">
          <Button
            variant="secondary"
            onClick={handleLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : 'Load older events'}
          </Button>
        </div>
      )}
    </div>
  );
}

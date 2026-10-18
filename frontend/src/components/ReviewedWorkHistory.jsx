import { useEffect, useState } from 'react';
import { getReviewHistory } from '../api';
import { getToken } from '../api/client';
import { PARENT_REVIEW_CHANGED } from '../api/parentReviewRefresh';
import { useAuth } from '../hooks/useApi';
import Button from './Button';
import ErrorAlert from './ErrorAlert';
import ParchmentCard from './journal/ParchmentCard';
import RuneBadge from './journal/RuneBadge';
import SubmissionTiming from './SubmissionTiming';
import ProofGallery from './ProofGallery';

function History({ kind, childId }) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(1);
  const [attempt, setAttempt] = useState(0);
  const [rows, setRows] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!open) return undefined;
    const token = getToken();
    let timer;
    const changed = (event) => {
      if (getToken() !== token || event.detail?.token !== token) return;
      clearTimeout(timer);
      // A bulk review can finish several writes together. Refresh once from
      // page one so new decisions cannot leave the saved history stale.
      timer = setTimeout(() => {
        if (getToken() !== token) return;
        setError('');
        setLoading(true);
        setHasMore(false);
        setPage(1);
        setAttempt((value) => value + 1);
      }, 60);
    };
    window.addEventListener(PARENT_REVIEW_CHANGED, changed);
    return () => {
      clearTimeout(timer);
      window.removeEventListener(PARENT_REVIEW_CHANGED, changed);
    };
  }, [open]);
  useEffect(() => {
    if (!open) return undefined;
    const controller = new AbortController();
    const token = getToken();
    let current = true;
    getReviewHistory(kind, { userId: childId, page, signal: controller.signal }).then((data) => {
      if (!current || getToken() !== token) return;
      const items = Array.isArray(data) ? data : data?.results;
      if (!Array.isArray(items)) throw new Error('Could not read reviewed work. Try again.');
      const reviewed = items.filter((row) => ['approved', 'rejected'].includes(row.status)
        && (childId == null || String(row.user ?? row.user_id) === String(childId)));
      setRows((previous) => [...new Map([...(page === 1 ? [] : previous), ...reviewed].map((row) => [row.id, row])).values()]);
      setHasMore(!Array.isArray(data) && Boolean(data.next));
      setLoading(false);
    }).catch((failure) => {
      if (!current || getToken() !== token || failure.name === 'AbortError') return;
      setError(failure.message);
      setLoading(false);
    });
    return () => { current = false; controller.abort(); };
  }, [open, kind, childId, page, attempt]);
  const title = kind === 'chore' ? 'Reviewed chores' : 'Reviewed homework';
  return <details className="space-y-3" onToggle={(event) => {
    const next = event.currentTarget.open;
    setOpen(next);
    setError('');
    setLoading(next);
    if (next) { setRows([]); setPage(1); }
  }}>
    <summary className="min-h-11 cursor-pointer font-body font-semibold text-body text-ink-primary">{title}</summary>
    <div className="space-y-3">
      {rows.map((row) => <ParchmentCard key={row.id} className="space-y-2">
        <div className="flex flex-wrap justify-between gap-2">
          <p className="font-body font-semibold text-body break-words">{row.user_name} · {row.chore_title || row.assignment_title}</p>
          <RuneBadge tone={row.status === 'approved' ? 'moss' : 'ember'}>{row.status === 'approved' ? 'Approved' : 'Rejected'}</RuneBadge>
        </div>
        <SubmissionTiming record={row} kind={kind} />
        {row.notes && <p className="font-body text-caption text-ink-secondary whitespace-pre-wrap break-words">{row.notes}</p>}
        {kind === 'homework' && <ProofGallery proofs={row.proofs || []} />}
      </ParchmentCard>)}
      {loading && <p role="status" className="font-body text-caption text-ink-secondary">Loading reviewed work…</p>}
      <ErrorAlert message={error} />
      {open && !loading && !error && rows.length === 0 && <p className="font-body text-caption text-ink-secondary">No reviewed work yet.</p>}
      {error && <Button variant="secondary" size="sm" onClick={() => { setError(''); setLoading(true); setAttempt((value) => value + 1); }}>Retry reviewed work</Button>}
      {hasMore && !error && <Button variant="secondary" size="sm" disabled={loading} onClick={() => { setLoading(true); setPage((value) => value + 1); }}>Load more reviewed work</Button>}
    </div>
  </details>;
}

export default function ReviewedWorkHistory({ kind, childId }) {
  const { user } = useAuth();
  // Callers pass the child selected by useChildContext only after the current
  // account's roster verifies it. Never turn an absent selection into an
  // implicit family-wide history request.
  if (user?.role !== 'parent' || !Number.isSafeInteger(Number(childId)) || Number(childId) < 1) return null;
  const scope = `${user.id}:${user.family?.id}:${getToken()}:${kind}:${childId ?? 'all'}`;
  return <History key={scope} kind={kind} childId={childId} />;
}

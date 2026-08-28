import { useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import {
  getTimecards, getTimecard, approveTimecard, disputeTimecard, markTimecardPaid,
  downloadTimecardsCsv,
} from '../api';
import { useApi } from '../hooks/useApi';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentSkeleton from '../components/ParchmentSkeleton';
import StatusBadge from '../components/StatusBadge';
import ParchmentCard from '../components/journal/ParchmentCard';
import { ScrollIcon } from '../components/icons/JournalIcons';
import { useRole } from '../hooks/useRole';
import Button from '../components/Button';
import PageShell from '../components/layout/PageShell';
import { formatCurrency, formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function Timecards() {
  const { isParent } = useRole();
  const { data, loading, error: loadError, reload } = useApi(getTimecards);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState('');
  const [error, setError] = useState('');
  const [exportError, setExportError] = useState('');
  // id of the timecard whose approve / dispute / mark-paid request is in
  // flight. `markTimecardPaid` has no server-side status guard, so a
  // double-tap really does post two payout rows.
  const [pendingId, setPendingId] = useState(null);
  // Per-row refs keyed by timecard id so we can scroll the expanded card
  // back into view on mobile — without this, expanding a mid-list card
  // pushes its detail below the fold and the user has to scroll manually.
  const rowRefs = useRef({});

  const timecards = normalizeList(data);

  const loadDetail = async (id) => {
    setDetail(null);
    setDetailError('');
    try {
      const d = await getTimecard(id);
      setDetail(d);
    } catch (err) {
      // Without this the promise rejected unhandled and the row simply
      // never opened — indistinguishable from a dead tap.
      setDetailError(err?.message || 'Could not open this week.');
      return;
    }
    // After the detail mounts, nudge the now-tall card into view. Wrapped
    // in requestAnimationFrame so the height transition has started and
    // ``scrollIntoView`` lands on the post-expansion geometry rather than
    // the pre-expansion one. jsdom doesn't implement scrollIntoView, so
    // the typeof check keeps tests quiet without skipping behavior in the
    // real browser.
    requestAnimationFrame(() => {
      const el = rowRefs.current[id];
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    });
  };

  const toggleExpand = (id) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      setDetailError('');
      return;
    }
    setExpandedId(id);
    loadDetail(id);
  };

  const handleExport = async () => {
    setExportError('');
    try {
      const blob = await downloadTimecardsCsv();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'timecards.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err?.message || 'Could not export timecards.');
    }
  };

  const handleAction = async (id, action) => {
    if (pendingId) return;
    setError('');
    setPendingId(id);
    try {
      if (action === 'approve') await approveTimecard(id, '');
      else if (action === 'dispute') await disputeTimecard(id);
      else if (action === 'pay') {
        const tc = timecards.find((t) => t.id === id);
        await markTimecardPaid(id, tc?.total_earnings);
      }
      await reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setPendingId(null);
    }
  };

  if (loading) return (
    <PageShell rhythm="loose" animate={false}>
      <ParchmentSkeleton variant="card" />
      <ParchmentSkeleton variant="list" count={5} />
    </PageShell>
  );

  return (
    <PageShell rhythm="loose">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the wages · every week sealed & stamped, rolled up from your daily clock-ins
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Wages
          </h1>
        </div>
        <Button
          size="sm"
          variant="ghost"
          onClick={handleExport}
          className="flex items-center gap-1"
          title="Export timecards to CSV"
        >
          <Download size={14} /> Export CSV
        </Button>
      </header>

      {exportError && <ErrorAlert message={exportError} />}
      <ErrorAlert message={error} />

      {/* A failed list fetch used to read as "no weeks logged yet" — data
          loss, as far as a kid on spotty wifi could tell — with no way back
          short of force-quitting the installed app. */}
      {loadError ? (
        <ErrorAlert message={`Couldn't load your wages. ${loadError}`} onRetry={reload} />
      ) : timecards.length === 0 ? (
        <EmptyState icon={<ScrollIcon size={36} />}>
          No weeks logged yet. Clock in on a venture to begin inking the ledger.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {timecards.map((tc) => (
            <motion.div
              key={tc.id}
              layout
              ref={(el) => {
                if (el) rowRefs.current[tc.id] = el;
                else delete rowRefs.current[tc.id];
              }}
            >
              <ParchmentCard className="overflow-hidden" seal={tc.status === 'paid'}>
                <button
                  type="button"
                  onClick={() => toggleExpand(tc.id)}
                  className="w-full flex items-center justify-between text-left gap-3 flex-wrap"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-script text-caption text-ink-whisper uppercase tracking-wider">
                      week of
                    </div>
                    <div className="font-display text-lede text-ink-primary leading-tight truncate">
                      {formatDate(tc.week_start)}
                    </div>
                    {isParent && tc.username && (
                      <div className="font-body text-caption text-ink-secondary mt-0.5 truncate">
                        {tc.username}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                      <div className="font-rune font-bold text-body text-ink-primary tabular-nums">
                        {tc.total_hours}h
                      </div>
                      <div className="font-rune font-bold text-body text-moss tabular-nums">
                        {formatCurrency(tc.total_earnings)}
                      </div>
                    </div>
                    <StatusBadge status={tc.status} />
                    {expandedId === tc.id ? (
                      <ChevronUp size={16} className="text-ink-secondary" />
                    ) : (
                      <ChevronDown size={16} className="text-ink-secondary" />
                    )}
                  </div>
                </button>

                {/* Opens on tap even before the detail lands — otherwise
                    only the chevron moves and a slow fetch reads as a
                    dead row. */}
                {expandedId === tc.id && !detail && !detailError && (
                  <div className="mt-4 pt-4 border-t border-ink-page-shadow">
                    <ParchmentSkeleton variant="list" count={3} />
                  </div>
                )}
                {expandedId === tc.id && detailError && (
                  <div className="mt-4 pt-4 border-t border-ink-page-shadow">
                    <ErrorAlert message={detailError} onRetry={() => loadDetail(tc.id)} />
                  </div>
                )}

                <AnimatePresence>
                  {expandedId === tc.id && detail && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-4 pt-4 border-t border-ink-page-shadow space-y-2">
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-center text-caption mb-3">
                          <div className="rounded-lg bg-ink-page/60 py-2 border border-ink-page-shadow/60">
                            <div className="font-script text-ink-whisper">Hourly</div>
                            <div className="font-rune font-bold text-ink-primary tabular-nums">
                              {formatCurrency(detail.hourly_earnings)}
                            </div>
                          </div>
                          <div className="rounded-lg bg-ink-page/60 py-2 border border-ink-page-shadow/60">
                            <div className="font-script text-ink-whisper">Bonuses</div>
                            <div className="font-rune font-bold text-ink-primary tabular-nums">
                              {formatCurrency(detail.bonus_earnings)}
                            </div>
                          </div>
                          <div className="rounded-lg bg-moss/10 py-2 border border-moss/40">
                            <div className="font-script text-ink-whisper">Total</div>
                            <div className="font-rune font-bold text-moss tabular-nums">
                              {formatCurrency(detail.total_earnings)}
                            </div>
                          </div>
                        </div>
                        <div className="font-script text-tiny text-ink-whisper text-center -mt-1 mb-2">
                          hourly comes from clocked time · bonuses are completion and milestone payouts
                        </div>
                        {detail.entries?.map((e) => (
                          <div
                            key={e.id}
                            className="flex justify-between text-caption py-1.5 border-b border-ink-page-shadow/40 last:border-0"
                          >
                            <div>
                              <span className="font-body font-medium text-ink-primary">
                                {e.project_title}
                              </span>
                              <span className="font-script text-ink-whisper ml-2">
                                {formatDate(e.clock_in)}
                              </span>
                            </div>
                            <span className="font-rune text-ink-secondary tabular-nums">
                              {e.duration_minutes ? formatDuration(e.duration_minutes) : '—'}
                            </span>
                          </div>
                        ))}
                        {isParent && tc.status === 'pending' && (
                          <div className="flex gap-2 pt-2">
                            <Button
                              variant="success"
                              size="sm"
                              onClick={() => handleAction(tc.id, 'approve')}
                              disabled={pendingId !== null}
                              className="flex-1"
                            >
                              {pendingId === tc.id ? 'Working…' : 'Approve'}
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleAction(tc.id, 'dispute')}
                              disabled={pendingId !== null}
                              className="flex-1"
                            >
                              Dispute
                            </Button>
                          </div>
                        )}
                        {isParent && tc.status === 'approved' && (
                          <Button
                            size="sm"
                            onClick={() => handleAction(tc.id, 'pay')}
                            disabled={pendingId !== null}
                            className="w-full"
                          >
                            {pendingId === tc.id
                              ? 'Marking as paid…'
                              : `Mark as paid (${formatCurrency(tc.total_earnings)})`}
                          </Button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </ParchmentCard>
            </motion.div>
          ))}
        </div>
      )}
    </PageShell>
  );
}

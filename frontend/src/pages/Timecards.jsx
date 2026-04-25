import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import { getTimecards, getTimecard, approveTimecard, disputeTimecard, markTimecardPaid } from '../api';
import { useApi } from '../hooks/useApi';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import StatusBadge from '../components/StatusBadge';
import ParchmentCard from '../components/journal/ParchmentCard';
import { ScrollIcon } from '../components/icons/JournalIcons';
import { useRole } from '../hooks/useRole';
import Button from '../components/Button';
import { formatCurrency, formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function Timecards() {
  const { isParent } = useRole();
  const { data, loading, reload } = useApi(getTimecards);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');

  const timecards = normalizeList(data);

  const toggleExpand = async (id) => {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(id);
    const d = await getTimecard(id);
    setDetail(d);
  };

  const handleAction = async (id, action) => {
    setError('');
    try {
      if (action === 'approve') await approveTimecard(id, '');
      else if (action === 'dispute') await disputeTimecard(id);
      else if (action === 'pay') {
        const tc = timecards.find((t) => t.id === id);
        await markTimecardPaid(id, tc?.total_earnings);
      }
      reload();
    } catch (err) {
      setError(err.message);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the wages · every week sealed & stamped, rolled up from your daily clock-ins
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Wages
          </h1>
        </div>
        <a
          href="/api/export/timecards/"
          className="flex items-center gap-1.5 font-script text-sm text-sheikah-teal-deep hover:text-sheikah-teal transition-colors"
        >
          <Download size={14} /> scribe a copy (CSV)
        </a>
      </header>

      <ErrorAlert message={error} />

      {timecards.length === 0 ? (
        <EmptyState icon={<ScrollIcon size={36} />}>
          No weeks logged yet. Clock in on a venture to begin inking the ledger.
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {timecards.map((tc) => (
            <motion.div key={tc.id} layout>
              <ParchmentCard className="overflow-hidden" seal={tc.status === 'paid'}>
                <button
                  type="button"
                  onClick={() => toggleExpand(tc.id)}
                  className="w-full flex items-center justify-between text-left"
                >
                  <div>
                    <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
                      week of
                    </div>
                    <div className="font-display text-lg text-ink-primary leading-tight">
                      {formatDate(tc.week_start)}
                    </div>
                    {isParent && tc.username && (
                      <div className="font-body text-xs text-ink-secondary mt-0.5">
                        {tc.username}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="font-rune font-bold text-sm text-ink-primary tabular-nums">
                        {tc.total_hours}h
                      </div>
                      <div className="font-rune font-bold text-sm text-moss tabular-nums">
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

                <AnimatePresence>
                  {expandedId === tc.id && detail && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-4 pt-4 border-t border-ink-page-shadow space-y-2">
                        <div className="grid grid-cols-3 gap-2 text-center text-xs mb-3">
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
                            className="flex justify-between text-xs py-1.5 border-b border-ink-page-shadow/40 last:border-0"
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
                              className="flex-1"
                            >
                              Approve
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleAction(tc.id, 'dispute')}
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
                            className="w-full"
                          >
                            Mark as Paid ({formatCurrency(tc.total_earnings)})
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
    </div>
  );
}

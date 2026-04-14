import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import { getTimecards, getTimecard, approveTimecard, disputeTimecard, markTimecardPaid } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import EmptyState from '../components/EmptyState';
import Loader from '../components/Loader';
import StatusBadge from '../components/StatusBadge';
import { useRole } from '../hooks/useRole';
import { buttonPrimary, buttonSecondary, buttonSuccess } from '../constants/styles';
import { formatCurrency, formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function Timecards() {
  const { isParent } = useRole();
  const { data, loading, reload } = useApi(getTimecards);
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);

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
    try {
      if (action === 'approve') await approveTimecard(id, '');
      else if (action === 'dispute') await disputeTimecard(id);
      else if (action === 'pay') {
        const tc = timecards.find(t => t.id === id);
        await markTimecardPaid(id, tc?.total_earnings);
      }
      reload();
    } catch (err) {
      alert(err.message);
    }
  };

  if (loading) return <Loader />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Timecards</h1>
        <a
          href="/api/export/timecards/"
          className="flex items-center gap-1.5 text-sm text-forge-text-dim hover:text-amber-highlight transition-colors"
        >
          <Download size={14} /> Export CSV
        </a>
      </div>

      {timecards.length === 0 ? (
        <EmptyState>No timecards yet</EmptyState>
      ) : (
        <div className="space-y-3">
          {timecards.map((tc) => (
            <motion.div key={tc.id} layout>
              <Card className="overflow-hidden">
                <div
                  className="flex items-center justify-between cursor-pointer"
                  onClick={() => toggleExpand(tc.id)}
                >
                  <div>
                    <div className="font-medium text-sm">
                      Week of {formatDate(tc.week_start)}
                    </div>
                    {isParent && tc.username && (
                      <div className="text-xs text-forge-text-dim">{tc.username}</div>
                    )}
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="font-heading font-bold text-sm">{tc.total_hours}h</div>
                      <div className="font-heading text-green-400 text-sm font-bold">{formatCurrency(tc.total_earnings)}</div>
                    </div>
                    <StatusBadge status={tc.status} />
                    {expandedId === tc.id ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </div>
                </div>

                <AnimatePresence>
                  {expandedId === tc.id && detail && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      className="overflow-hidden"
                    >
                      <div className="mt-4 pt-4 border-t border-forge-border space-y-2">
                        <div className="grid grid-cols-3 gap-2 text-center text-xs mb-3">
                          <div>
                            <div className="text-forge-text-dim">Hourly</div>
                            <div className="font-heading font-bold">{formatCurrency(detail.hourly_earnings)}</div>
                          </div>
                          <div>
                            <div className="text-forge-text-dim">Bonuses</div>
                            <div className="font-heading font-bold">{formatCurrency(detail.bonus_earnings)}</div>
                          </div>
                          <div>
                            <div className="text-forge-text-dim">Total</div>
                            <div className="font-heading font-bold text-green-400">{formatCurrency(detail.total_earnings)}</div>
                          </div>
                        </div>
                        {detail.entries?.map((e) => (
                          <div key={e.id} className="flex justify-between text-xs py-1 border-b border-forge-border/50 last:border-0">
                            <div>
                              <span className="font-medium">{e.project_title}</span>
                              <span className="text-forge-text-dim ml-2">
                                {formatDate(e.clock_in)}
                              </span>
                            </div>
                            <span className="font-heading">
                              {e.duration_minutes ? formatDuration(e.duration_minutes) : '—'}
                            </span>
                          </div>
                        ))}
                        {isParent && tc.status === 'pending' && (
                          <div className="flex gap-2 pt-2">
                            <button onClick={() => handleAction(tc.id, 'approve')} className={`flex-1 py-2 text-sm ${buttonSuccess}`}>
                              Approve
                            </button>
                            <button onClick={() => handleAction(tc.id, 'dispute')} className={`flex-1 py-2 text-sm ${buttonSecondary}`}>
                              Dispute
                            </button>
                          </div>
                        )}
                        {isParent && tc.status === 'approved' && (
                          <button onClick={() => handleAction(tc.id, 'pay')} className={`w-full py-2 text-sm ${buttonPrimary}`}>
                            Mark as Paid ({formatCurrency(tc.total_earnings)})
                          </button>
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

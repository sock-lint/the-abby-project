import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { DollarSign, TrendingUp, ArrowDownRight, ArrowUpRight, ArrowRightLeft, Target, Plus, Download, Filter, X } from 'lucide-react';
import {
  getBalance, adjustPayment, getChildren,
  getPaymentLedger, downloadPaymentLedgerCsv,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useFormState } from '../hooks/useFormState';
import { useRole } from '../hooks/useRole';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import DeckleDivider from '../components/journal/DeckleDivider';
import RuneBadge from '../components/journal/RuneBadge';
import { formatCurrency } from '../utils/format';
import { normalizeList } from '../utils/api';
import Button from '../components/Button';
import { TextField, SelectField } from '../components/form';

// Each ledger category maps to a journal-compatible tone rather than a
// neon accent. Icons remain lucide-react glyphs, colored via tone class.
const typeIcons = {
  hourly:                  { icon: TrendingUp,    tone: 'text-sheikah-teal-deep' },
  project_bonus:           { icon: TrendingUp,    tone: 'text-moss' },
  bounty_payout:           { icon: Target,        tone: 'text-royal' },
  milestone_bonus:         { icon: TrendingUp,    tone: 'text-moss' },
  materials_reimbursement: { icon: ArrowUpRight,  tone: 'text-sheikah-teal-deep' },
  payout:                  { icon: ArrowDownRight, tone: 'text-ember-deep' },
  adjustment:              { icon: DollarSign,    tone: 'text-gold-leaf' },
  coin_exchange:           { icon: ArrowRightLeft, tone: 'text-gold-leaf' },
  chore_reward:            { icon: TrendingUp,    tone: 'text-moss' },
};

const typeLabels = {
  hourly: 'Hourly',
  project_bonus: 'Project Bonus',
  bounty_payout: 'Bounty',
  milestone_bonus: 'Milestone Bonus',
  materials_reimbursement: 'Reimbursement',
  payout: 'Payout',
  adjustment: 'Adjustment',
  coin_exchange: 'Coin Exchange',
  chore_reward: 'Chore Reward',
};

function PaymentAdjustModal({ onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    user_id: '', amount: '', description: '',
  });
  const onField = (k) => (e) => set({ [k]: e.target.value });
  const { data: childrenRes, loading: loadingChildren } = useApi(getChildren);
  const children = normalizeList(childrenRes);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await adjustPayment(parseInt(form.user_id), parseFloat(form.amount), form.description);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Adjust Balance" onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <SelectField
          label="Kid"
          value={form.user_id}
          onChange={onField('user_id')}
          required
          disabled={loadingChildren}
          helpText={loadingChildren ? 'Loading kids…' : (children.length === 0 ? 'No children in this family yet.' : null)}
        >
          <option value="" disabled>Pick a kid</option>
          {children.map((child) => (
            <option key={child.id} value={child.id}>
              {child.display_name || child.username}
            </option>
          ))}
        </SelectField>
        <TextField
          label={<>Amount <span className="text-ink-whisper">(positive = credit, negative = debit)</span></>}
          type="number"
          step="0.01"
          value={form.amount}
          onChange={onField('amount')}
          required
        />
        <TextField label="Description" value={form.description} onChange={onField('description')} placeholder="Reason for adjustment" />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-secondary hover:text-ink-primary">
            Cancel
          </button>
          <Button type="submit" size="sm" disabled={saving || !form.user_id}>
            {saving ? 'Adjusting…' : 'Adjust'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

export default function Payments() {
  const { isParent } = useRole();
  const { data, loading, error, reload } = useApi(getBalance);
  const [showAdjust, setShowAdjust] = useState(false);
  const [filters, setFilters] = useState({
    entry_types: [],   // multi-select array
    start_date: '',
    end_date: '',
    user_id: '',
  });
  const [filteredLedger, setFilteredLedger] = useState(null);
  const [filterLoading, setFilterLoading] = useState(false);
  const [exportError, setExportError] = useState('');
  const { data: childrenData } = useApi(
    isParent ? getChildren : () => Promise.resolve({ results: [] }),
    [isParent],
  );
  const children = useMemo(() => normalizeList(childrenData), [childrenData]);

  // Any filter active? Drives whether we fetch the ledger directly vs.
  // showing the summary's recent_transactions slice.
  const hasFilter = useMemo(
    () =>
      filters.entry_types.length > 0
      || !!filters.start_date
      || !!filters.end_date
      || !!filters.user_id,
    [filters],
  );

  // Re-fetch the filtered ledger when filters become active or change.
  // ``filteredLedger`` is only consumed in render when ``hasFilter`` is
  // true (see ``entriesToRender`` below), so we leave any stale value
  // sitting in state when filters are cleared rather than calling
  // setFilteredLedger(null) here — that would be a synchronous setState
  // inside an effect body for no externally-visible reason. The stale
  // value is shadowed at render time, and replaced wholesale on the
  // next filter activation.
  useEffect(() => {
    if (!hasFilter) return;
    // Marking "loading" before kicking off the fetch is a legitimate
    // synchronization-with-external-system pattern — the rule's
    // "don't setState in an effect" guidance targets effects that
    // should be derived state, not ones that wrap async network IO.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFilterLoading(true);
    const params = {
      start_date: filters.start_date || undefined,
      end_date: filters.end_date || undefined,
      user_id: filters.user_id || undefined,
      entry_type: filters.entry_types.length
        ? filters.entry_types.join(',')
        : undefined,
    };
    let cancelled = false;
    getPaymentLedger(params)
      .then((resp) => {
        if (cancelled) return;
        setFilteredLedger(normalizeList(resp));
      })
      .catch(() => {
        if (cancelled) return;
        setFilteredLedger([]);
      })
      .finally(() => {
        if (cancelled) return;
        setFilterLoading(false);
      });
    return () => { cancelled = true; };
  }, [filters, hasFilter]);

  const toggleEntryType = (type) => {
    setFilters((prev) => {
      const has = prev.entry_types.includes(type);
      return {
        ...prev,
        entry_types: has
          ? prev.entry_types.filter((t) => t !== type)
          : [...prev.entry_types, type],
      };
    });
  };

  const clearFilters = () =>
    setFilters({ entry_types: [], start_date: '', end_date: '', user_id: '' });

  const handleExport = async () => {
    setExportError('');
    try {
      const blob = await downloadPaymentLedgerCsv({
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        user_id: filters.user_id || undefined,
        entry_type: filters.entry_types.length
          ? filters.entry_types.join(',')
          : undefined,
      });
      // Trigger a real browser download — the blob comes back via fetch
      // so the auth header is honored, then we hand the bytes to the
      // browser via a temporary <a download> click.
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'payment-ledger.csv';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err?.message || 'Could not export the ledger.');
    }
  };

  if (loading) return <Loader />;
  if (error || !data) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        <ErrorAlert message={error || 'Could not load the coffers.'} />
        <Button variant="secondary" size="sm" onClick={reload}>
          Try again
        </Button>
      </div>
    );
  }

  const { balance, breakdown, recent_transactions } = data;
  // Render the filtered ledger when any filter is active; otherwise show
  // the small recent_transactions slice from the balance summary. The
  // ``hasFilter`` shadow is what lets the effect leave stale filteredLedger
  // values in state without leaking them into the UI.
  const entriesToRender = hasFilter
    ? (filteredLedger ?? [])
    : (recent_transactions ?? []);

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the coffers · every coin accounted for
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Coffers
          </h1>
        </div>
        {isParent && (
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={handleExport}
              className="flex items-center gap-1"
              title="Export current view to CSV"
            >
              <Download size={14} /> Export CSV
            </Button>
            <Button
              size="sm"
              onClick={() => setShowAdjust(true)}
              className="flex items-center gap-1"
            >
              <Plus size={14} /> Adjust Balance
            </Button>
          </div>
        )}
      </header>

      {exportError && <ErrorAlert message={exportError} />}

      {/* Balance hero — rendered as a wax-sealed ledger entry */}
      <motion.div initial={{ scale: 0.96, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
        <ParchmentCard flourish tone="bright" className="text-center py-8">
          <div className="font-script text-ink-whisper text-sm uppercase tracking-widest">
            current balance
          </div>
          <div
            className={`font-display font-semibold text-5xl md:text-6xl tabular-nums ${
              balance >= 0 ? 'text-moss' : 'text-ember-deep'
            }`}
          >
            {formatCurrency(balance)}
          </div>
        </ParchmentCard>
      </motion.div>

      {/* Breakdown */}
      {breakdown && Object.keys(breakdown).length > 0 && (
        <section>
          <DeckleDivider glyph="wax-seal" label="breakdown" />
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(breakdown).map(([type, amount]) => {
              const { icon: Icon, tone } = typeIcons[type] || typeIcons.adjustment;
              return (
                <ParchmentCard key={type} tone="bright">
                  <div className="flex items-center gap-2 mb-1">
                    <Icon size={14} className={tone} />
                    <span className="font-script text-xs text-ink-whisper uppercase tracking-wider">
                      {typeLabels[type] || type}
                    </span>
                  </div>
                  <div
                    className={`font-display font-semibold text-xl tabular-nums ${
                      amount >= 0 ? 'text-ink-primary' : 'text-ember-deep'
                    }`}
                  >
                    {formatCurrency(amount)}
                  </div>
                </ParchmentCard>
              );
            })}
          </div>
        </section>
      )}

      {/* Filter strip — entry-type pills, optional date range + child select */}
      <section aria-labelledby="ledger-filters-heading">
        <DeckleDivider glyph="flourish-corner" label="recent entries" />
        <div className="flex flex-wrap items-center gap-1.5 mb-2" id="ledger-filters-heading">
          <Filter size={12} className="text-ink-whisper" aria-hidden="true" />
          {Object.entries(typeLabels).map(([type, label]) => {
            const active = filters.entry_types.includes(type);
            return (
              <button
                key={type}
                type="button"
                onClick={() => toggleEntryType(type)}
                aria-pressed={active}
                className={`px-2 py-0.5 text-tiny font-script rounded-full border transition-colors ${
                  active
                    ? 'bg-sheikah-teal-deep/15 text-sheikah-teal-deep border-sheikah-teal-deep/40'
                    : 'bg-ink-page-aged hover:bg-ink-page-shadow/40 text-ink-whisper border-ink-page-shadow/30'
                }`}
              >
                {label}
              </button>
            );
          })}
          {hasFilter && (
            <button
              type="button"
              onClick={clearFilters}
              className="px-2 py-0.5 text-tiny font-script rounded-full bg-ember-deep/10 text-ember-deep border border-ember-deep/30 hover:bg-ember-deep/20 flex items-center gap-1"
              aria-label="Clear all filters"
            >
              <X size={10} aria-hidden="true" /> clear
            </button>
          )}
        </div>
        {isParent && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-2 mb-2">
            <input
              type="date"
              value={filters.start_date}
              onChange={(e) => setFilters((p) => ({ ...p, start_date: e.target.value }))}
              aria-label="Filter from date"
              className="px-2 py-1 text-tiny font-script rounded border border-ink-page-shadow/30 bg-ink-page-aged"
            />
            <input
              type="date"
              value={filters.end_date}
              onChange={(e) => setFilters((p) => ({ ...p, end_date: e.target.value }))}
              aria-label="Filter to date"
              className="px-2 py-1 text-tiny font-script rounded border border-ink-page-shadow/30 bg-ink-page-aged"
            />
            <SelectField
              variant="filter"
              aria-label="Filter by kid"
              value={filters.user_id}
              onChange={(e) => setFilters((p) => ({ ...p, user_id: e.target.value }))}
            >
              <option value="">All kids</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.display_name || c.username}
                </option>
              ))}
            </SelectField>
          </div>
        )}
      </section>

      {/* Ledger entries — switches to filtered ledger when any filter is active */}
      {entriesToRender.length > 0 && (
        <section>
          <div className="space-y-2">
            {filterLoading && (
              <div className="font-script text-tiny text-ink-whisper">filtering…</div>
            )}
            {entriesToRender.map((tx) => {
              const { icon: Icon, tone } = typeIcons[tx.entry_type] || typeIcons.adjustment;
              const isPositive = parseFloat(tx.amount) >= 0;
              return (
                <ParchmentCard
                  key={tx.id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div
                      className={`w-9 h-9 shrink-0 rounded-full bg-ink-page border border-ink-page-shadow flex items-center justify-center ${tone}`}
                    >
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="font-body text-sm font-medium text-ink-primary">
                        {typeLabels[tx.entry_type] || tx.entry_type}
                      </div>
                      <div className="font-script text-xs text-ink-whisper truncate">
                        {tx.description}
                      </div>
                    </div>
                  </div>
                  <div
                    className={`font-rune font-bold text-sm tabular-nums shrink-0 ${
                      isPositive ? 'text-moss' : 'text-ember-deep'
                    }`}
                  >
                    {isPositive ? '+' : ''}
                    {formatCurrency(tx.amount)}
                  </div>
                </ParchmentCard>
              );
            })}
          </div>
        </section>
      )}

      {!breakdown && !entriesToRender.length && (
        <RuneBadge tone="ink">nothing inked yet — complete some quests to see entries here</RuneBadge>
      )}
      {hasFilter && entriesToRender.length === 0 && !filterLoading && (
        <RuneBadge tone="ink">no entries match those filters</RuneBadge>
      )}

      {showAdjust && (
        <PaymentAdjustModal
          onClose={() => setShowAdjust(false)}
          onSaved={() => { setShowAdjust(false); reload(); }}
        />
      )}
    </div>
  );
}

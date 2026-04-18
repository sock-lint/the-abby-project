import { useState } from 'react';
import { motion } from 'framer-motion';
import { DollarSign, TrendingUp, ArrowDownRight, ArrowUpRight, ArrowRightLeft, Target, Plus } from 'lucide-react';
import { getBalance, adjustPayment } from '../api';
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
import Button from '../components/Button';
import { TextField } from '../components/form';

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
        <TextField label="Child User ID" type="number" value={form.user_id} onChange={onField('user_id')} required placeholder="Enter child user ID" />
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
          <Button type="submit" size="sm" disabled={saving}>
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
          <Button
            size="sm"
            onClick={() => setShowAdjust(true)}
            className="flex items-center gap-1"
          >
            <Plus size={14} /> Adjust Balance
          </Button>
        )}
      </header>

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

      {/* Recent transactions */}
      {recent_transactions?.length > 0 && (
        <section>
          <DeckleDivider glyph="flourish-corner" label="recent entries" />
          <div className="space-y-2">
            {recent_transactions.map((tx) => {
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

      {!breakdown && !recent_transactions?.length && (
        <RuneBadge tone="ink">nothing inked yet — complete some quests to see entries here</RuneBadge>
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

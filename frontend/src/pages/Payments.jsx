import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { DollarSign, TrendingUp, TrendingDown, ArrowDownRight, ArrowUpRight, ArrowRightLeft, Target, Plus, X } from 'lucide-react';
import { getBalance, adjustPayment } from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { formatCurrency } from '../utils/format';

const inputClass = 'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base focus:outline-none focus:border-amber-primary';

const typeIcons = {
  hourly: { icon: TrendingUp, color: 'text-blue-400' },
  project_bonus: { icon: TrendingUp, color: 'text-green-400' },
  bounty_payout: { icon: Target, color: 'text-fuchsia-400' },
  milestone_bonus: { icon: TrendingUp, color: 'text-emerald-400' },
  materials_reimbursement: { icon: ArrowUpRight, color: 'text-cyan-400' },
  payout: { icon: ArrowDownRight, color: 'text-red-400' },
  adjustment: { icon: DollarSign, color: 'text-yellow-400' },
  coin_exchange: { icon: ArrowRightLeft, color: 'text-amber-400' },
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
};

function PaymentAdjustModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ user_id: '', amount: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true); setError('');
    try {
      await adjustPayment(parseInt(form.user_id), parseFloat(form.amount), form.description);
      onSaved();
    } catch (err) { setError(err.message); } finally { setSaving(false); }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      >
        <div className="absolute inset-0 bg-black/60" onClick={onClose} />
        <motion.div
          className="relative w-full md:max-w-md bg-forge-card border border-forge-border rounded-t-2xl md:rounded-2xl p-5"
          initial={{ y: '100%' }} animate={{ y: 0 }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading text-lg font-bold">Adjust Balance</h3>
            <button onClick={onClose} className="text-forge-text-dim hover:text-forge-text"><X size={20} /></button>
          </div>
          <ErrorAlert message={error} />
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Child User ID</label>
              <input className={inputClass} type="number" value={form.user_id} onChange={set('user_id')} required placeholder="Enter child user ID" />
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Amount (positive to credit, negative to debit)</label>
              <input className={inputClass} type="number" step="0.01" value={form.amount} onChange={set('amount')} required />
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
              <input className={inputClass} value={form.description} onChange={set('description')} placeholder="Reason for adjustment" />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
              <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">
                {saving ? 'Adjusting...' : 'Adjust'}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export default function Payments() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';
  const { data, loading, reload } = useApi(getBalance);
  const [showAdjust, setShowAdjust] = useState(false);

  if (loading) return <Loader />;
  if (!data) return null;

  const { balance, breakdown, recent_transactions } = data;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Payments</h1>
        {isParent && (
          <button
            onClick={() => setShowAdjust(true)}
            className="flex items-center gap-1 bg-amber-primary hover:bg-amber-highlight text-black text-xs font-semibold px-3 py-1.5 rounded-lg"
          >
            <Plus size={14} /> Adjust Balance
          </button>
        )}
      </div>

      {/* Balance Card */}
      <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
        <Card className="text-center py-6">
          <div className="text-sm text-forge-text-dim mb-1">Current Balance</div>
          <div className={`font-heading text-5xl font-bold ${balance >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatCurrency(balance)}
          </div>
        </Card>
      </motion.div>

      {/* Breakdown */}
      {breakdown && Object.keys(breakdown).length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Breakdown</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {Object.entries(breakdown).map(([type, amount]) => {
              const { icon: Icon, color } = typeIcons[type] || typeIcons.adjustment;
              return (
                <Card key={type}>
                  <div className="flex items-center gap-2 mb-1">
                    <Icon size={14} className={color} />
                    <span className="text-xs text-forge-text-dim">{typeLabels[type] || type}</span>
                  </div>
                  <div className={`font-heading font-bold ${amount >= 0 ? 'text-forge-text' : 'text-red-400'}`}>
                    {formatCurrency(amount)}
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* Recent Transactions */}
      {recent_transactions?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Recent Transactions</h2>
          <div className="space-y-2">
            {recent_transactions.map((tx) => {
              const { icon: Icon, color } = typeIcons[tx.entry_type] || typeIcons.adjustment;
              const isPositive = parseFloat(tx.amount) >= 0;
              return (
                <Card key={tx.id} className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className={`w-8 h-8 shrink-0 rounded-full bg-forge-muted flex items-center justify-center ${color}`}>
                      <Icon size={16} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{typeLabels[tx.entry_type] || tx.entry_type}</div>
                      <div className="text-xs text-forge-text-dim truncate">{tx.description}</div>
                    </div>
                  </div>
                  <div className={`font-heading font-bold text-sm shrink-0 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                    {isPositive ? '+' : ''}{formatCurrency(tx.amount)}
                  </div>
                </Card>
              );
            })}
          </div>
        </div>
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

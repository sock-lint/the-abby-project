import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRightLeft, Coins, DollarSign } from 'lucide-react';
import { getBalance, requestExchange } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useApi } from '../../hooks/useApi';
import { buttonPrimary, inputClass } from '../../constants/styles';
import { formatCurrency } from '../../utils/format';

export default function CoinExchangeModal({ exchangeRate, onClose, onSaved }) {
  const [dollarAmount, setDollarAmount] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const { data: balData } = useApi(getBalance);

  const moneyBalance = balData?.balance ?? 0;
  const rate = exchangeRate ?? 10;
  const coins = dollarAmount ? Math.floor(parseFloat(dollarAmount) * rate) : 0;
  const valid = parseFloat(dollarAmount) >= 1 && parseFloat(dollarAmount) <= moneyBalance;

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await requestExchange(parseFloat(dollarAmount));
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormModal title="Exchange Money for Coins" onClose={onClose} size="md" scroll={false}>
      <ErrorAlert message={error} />

      <div className="flex items-center justify-between text-sm mb-4 p-3 bg-forge-bg rounded-lg border border-forge-border">
        <span className="text-forge-text-dim">Exchange Rate</span>
        <span className="font-bold text-amber-highlight">$1.00 = {rate} coins</span>
      </div>

      <div className="flex items-center justify-between text-sm mb-4 p-3 bg-forge-bg rounded-lg border border-forge-border">
        <span className="text-forge-text-dim">Your Balance</span>
        <span className="font-bold text-green-400">{formatCurrency(moneyBalance)}</span>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Dollar Amount (min $1.00)</label>
          <input
            className={inputClass}
            type="number"
            min="1"
            step="0.01"
            value={dollarAmount}
            onChange={(e) => setDollarAmount(e.target.value)}
            required
            placeholder="0.00"
          />
        </div>
        {dollarAmount && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center justify-center gap-2 p-3 bg-amber-primary/10 border border-amber-primary/30 rounded-lg"
          >
            <DollarSign size={16} className="text-green-400" />
            <span className="text-sm">{formatCurrency(dollarAmount || 0)}</span>
            <ArrowRightLeft size={14} className="text-forge-text-dim" />
            <Coins size={16} className="text-amber-highlight" />
            <span className="text-sm font-bold text-amber-highlight">{coins} coins</span>
          </motion.div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">
            Cancel
          </button>
          <button type="submit" disabled={saving || !valid} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Requesting...' : 'Request Exchange'}
          </button>
        </div>
        <p className="text-[10px] text-forge-text-dim text-center">Requires parent approval</p>
      </form>
    </FormModal>
  );
}

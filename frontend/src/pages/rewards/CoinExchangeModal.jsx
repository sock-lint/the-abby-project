import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRightLeft, Coins, DollarSign } from 'lucide-react';
import { getBalance, requestExchange } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useApi } from '../../hooks/useApi';
import Button from '../../components/Button';
import { TextField } from '../../components/form';
import { formatCurrency } from '../../utils/format';

const MIN_DOLLARS = 1;

export default function CoinExchangeModal({
  exchangeRate, rateError, onRetryRate, onClose, onSaved,
}) {
  const [dollarAmount, setDollarAmount] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const {
    data: balData, loading: loadingBalance, error: balanceError, reload: reloadBalance,
  } = useApi(getBalance);

  // Never fall back to 0 — a confident "Your Balance $0.00" while the fetch
  // is still in flight (or after it failed) reads as "you have no money",
  // and every amount the kid types then greys the button out for no visible
  // reason.
  const balanceKnown = !loadingBalance && !balanceError;
  const moneyBalance = balanceKnown ? (balData?.balance ?? 0) : null;
  const rate = exchangeRate ?? 10;
  const parsed = parseFloat(dollarAmount);
  const hasAmount = Number.isFinite(parsed);
  const coins = hasAmount ? Math.floor(parsed * rate) : 0;
  const valid = hasAmount
    && parsed >= MIN_DOLLARS
    && balanceKnown
    && parsed <= moneyBalance;

  // One plain-English reason the Request button is off, so "over balance",
  // "under the minimum" and "balance still loading" stop looking identical.
  // Real input problems read as errors; waiting-on-the-network reads as a hint.
  let amountError = null;
  let amountHint = null;
  if (hasAmount && parsed < MIN_DOLLARS) {
    amountError = `Minimum is ${formatCurrency(MIN_DOLLARS)}.`;
  } else if (hasAmount && loadingBalance) {
    amountHint = 'Checking your balance…';
  } else if (hasAmount && balanceError) {
    amountHint = "Your balance couldn't be loaded, so this can't be sent yet.";
  } else if (hasAmount && parsed > moneyBalance) {
    amountError = `You only have ${formatCurrency(moneyBalance)}.`;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await requestExchange(parsed);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Exchange money for coins" onClose={onClose}>
      <ErrorAlert message={error} />
      {balanceError && (
        <ErrorAlert
          message={`Couldn't load your money balance. ${balanceError}`}
          onRetry={reloadBalance}
          className="mb-3"
        />
      )}
      {rateError && (
        <ErrorAlert
          message={`Couldn't load the exchange rate — showing the usual ${rate} coins per $1.00.`}
          onRetry={onRetryRate}
          className="mb-3"
        />
      )}

      <div className="flex items-center justify-between text-body mb-4 p-3 bg-ink-page rounded-lg border border-ink-page-shadow">
        <span className="text-ink-whisper">Exchange rate</span>
        <span className="font-bold text-sheikah-teal-deep">$1.00 = {rate} coins</span>
      </div>

      <div className="flex items-center justify-between text-body mb-4 p-3 bg-ink-page rounded-lg border border-ink-page-shadow">
        <span className="text-ink-whisper">Your balance</span>
        {loadingBalance ? (
          <span className="font-script text-ink-whisper">checking…</span>
        ) : balanceError ? (
          <span className="font-script text-ember-deep">unavailable</span>
        ) : (
          <span className="font-bold text-moss">{formatCurrency(moneyBalance)}</span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField
          label="Dollar amount (min $1.00)"
          type="number"
          min="1"
          step="0.01"
          value={dollarAmount}
          onChange={(e) => setDollarAmount(e.target.value)}
          required
          placeholder="0.00"
          error={amountError}
          helpText={amountHint}
        />
        {dollarAmount && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-center justify-center gap-2 p-3 bg-sheikah-teal/10 border border-sheikah-teal-deep/30 rounded-lg"
          >
            <DollarSign size={16} className="text-moss" />
            <span className="text-body">{formatCurrency(dollarAmount || 0)}</span>
            <ArrowRightLeft size={14} className="text-ink-whisper" />
            <Coins size={16} className="text-sheikah-teal-deep" />
            <span className="text-body font-bold text-sheikah-teal-deep">{coins} coins</span>
          </motion.div>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" size="sm" disabled={saving || !valid}>
            {saving ? 'Requesting…' : 'Request exchange'}
          </Button>
        </div>
        <p className="text-micro text-ink-whisper text-center">Requires parent approval</p>
      </form>
    </BottomSheet>
  );
}

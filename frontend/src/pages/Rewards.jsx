import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Coins, Check, X, Clock, Gift, Plus, Pencil, Trash2, ArrowRightLeft, DollarSign } from 'lucide-react';
import {
  getRewards, redeemReward, getRedemptions, getCoinBalance,
  approveRedemption, denyRedemption,
  createReward, updateReward, deleteReward, adjustCoins,
  getExchangeRate, requestExchange, getExchangeRequests,
  approveExchange, denyExchange, getBalance,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { RARITY_COLORS, STATUS_COLORS } from '../constants/colors';
import { formatDate, formatDateTime } from '../utils/format';
import { normalizeList } from '../utils/api';

const inputClass = 'w-full bg-forge-bg border border-forge-border rounded-lg px-3 py-2 text-forge-text text-base focus:outline-none focus:border-amber-primary';
const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];

function RewardFormModal({ reward, onClose, onSaved }) {
  const isEdit = !!reward;
  const [form, setForm] = useState({
    name: reward?.name || '',
    description: reward?.description || '',
    icon: reward?.icon || '',
    cost_coins: reward?.cost_coins ?? '',
    rarity: reward?.rarity || 'common',
    stock: reward?.stock ?? '',
    requires_parent_approval: reward?.requires_parent_approval ?? true,
    is_active: reward?.is_active ?? true,
    order: reward?.order ?? 0,
  });
  const [imageFile, setImageFile] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const set = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    setForm({ ...form, [k]: val });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const fd = new FormData();
      fd.append('name', form.name);
      fd.append('description', form.description);
      fd.append('icon', form.icon);
      fd.append('cost_coins', parseInt(form.cost_coins) || 0);
      fd.append('rarity', form.rarity);
      if (form.stock !== '' && form.stock !== null) fd.append('stock', parseInt(form.stock));
      fd.append('requires_parent_approval', form.requires_parent_approval);
      fd.append('is_active', form.is_active);
      fd.append('order', parseInt(form.order) || 0);
      if (imageFile) fd.append('image', imageFile);
      if (isEdit) {
        await updateReward(reward.id, fd);
      } else {
        await createReward(fd);
      }
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end md:items-center justify-center"
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      >
        <div className="absolute inset-0 bg-black/60" onClick={onClose} />
        <motion.div
          className="relative w-full md:max-w-lg bg-forge-card border border-forge-border rounded-t-2xl md:rounded-2xl p-5 max-h-[85vh] overflow-y-auto"
          initial={{ y: '100%' }} animate={{ y: 0 }}
          transition={{ type: 'spring', damping: 30, stiffness: 300 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-heading text-lg font-bold">{isEdit ? 'Edit Reward' : 'New Reward'}</h3>
            <button onClick={onClose} className="text-forge-text-dim hover:text-forge-text"><X size={20} /></button>
          </div>
          <ErrorAlert message={error} />
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Name</label>
              <input className={inputClass} value={form.name} onChange={set('name')} required />
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
              <textarea className={inputClass} value={form.description} onChange={set('description')} rows={2} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Icon (emoji)</label>
                <input className={inputClass} value={form.icon} onChange={set('icon')} placeholder="🎁" />
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Cost (coins)</label>
                <input className={inputClass} type="number" min="0" value={form.cost_coins} onChange={set('cost_coins')} required />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Rarity</label>
                <select className={inputClass} value={form.rarity} onChange={set('rarity')}>
                  {RARITIES.map((r) => <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Stock (blank = unlimited)</label>
                <input className={inputClass} type="number" min="0" value={form.stock} onChange={set('stock')} placeholder="∞" />
              </div>
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Image</label>
              <input type="file" accept="image/*" onChange={(e) => setImageFile(e.target.files[0])} className="text-sm text-forge-text" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-forge-text-dim mb-1 block">Order</label>
                <input className={inputClass} type="number" value={form.order} onChange={set('order')} />
              </div>
              <div />
            </div>
            <div className="flex gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.requires_parent_approval} onChange={set('requires_parent_approval')} className="accent-amber-primary" />
                Requires approval
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_active} onChange={set('is_active')} className="accent-amber-primary" />
                Active
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
              <button type="submit" disabled={saving} className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50">
                {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
              </button>
            </div>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function CoinAdjustModal({ onClose, onSaved }) {
  const [form, setForm] = useState({ user_id: '', amount: '', description: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      await adjustCoins(parseInt(form.user_id), parseInt(form.amount), form.description);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
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
            <h3 className="font-heading text-lg font-bold">Adjust Coins</h3>
            <button onClick={onClose} className="text-forge-text-dim hover:text-forge-text"><X size={20} /></button>
          </div>
          <ErrorAlert message={error} />
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Child User ID</label>
              <input className={inputClass} type="number" value={form.user_id} onChange={set('user_id')} required placeholder="Enter child user ID" />
            </div>
            <div>
              <label className="text-xs text-forge-text-dim mb-1 block">Amount (positive to add, negative to deduct)</label>
              <input className={inputClass} type="number" value={form.amount} onChange={set('amount')} required />
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

function CoinExchangeModal({ exchangeRate, onClose, onSaved }) {
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
            <h3 className="font-heading text-lg font-bold">Exchange Money for Coins</h3>
            <button onClick={onClose} className="text-forge-text-dim hover:text-forge-text"><X size={20} /></button>
          </div>
          <ErrorAlert message={error} />

          <div className="flex items-center justify-between text-sm mb-4 p-3 bg-forge-bg rounded-lg border border-forge-border">
            <span className="text-forge-text-dim">Exchange Rate</span>
            <span className="font-bold text-amber-highlight">$1.00 = {rate} coins</span>
          </div>

          <div className="flex items-center justify-between text-sm mb-4 p-3 bg-forge-bg rounded-lg border border-forge-border">
            <span className="text-forge-text-dim">Your Balance</span>
            <span className="font-bold text-green-400">${Number(moneyBalance).toFixed(2)}</span>
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
                initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }}
                className="flex items-center justify-center gap-2 p-3 bg-amber-primary/10 border border-amber-primary/30 rounded-lg"
              >
                <DollarSign size={16} className="text-green-400" />
                <span className="text-sm">${parseFloat(dollarAmount || 0).toFixed(2)}</span>
                <ArrowRightLeft size={14} className="text-forge-text-dim" />
                <Coins size={16} className="text-amber-highlight" />
                <span className="text-sm font-bold text-amber-highlight">{coins} coins</span>
              </motion.div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
              <button
                type="submit"
                disabled={saving || !valid}
                className="px-4 py-2 bg-amber-primary hover:bg-amber-highlight text-black text-sm font-semibold rounded-lg disabled:opacity-50"
              >
                {saving ? 'Requesting...' : 'Request Exchange'}
              </button>
            </div>
            <p className="text-[10px] text-forge-text-dim text-center">Requires parent approval</p>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

export default function Rewards() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';

  const { data: rewardsData, loading: loadingRewards, reload: reloadRewards } = useApi(getRewards);
  const { data: redemptionsData, loading: loadingRedemptions, reload: reloadRedemptions } = useApi(getRedemptions);
  const { data: balanceData, loading: loadingBalance, reload: reloadBalance } = useApi(getCoinBalance);
  const [error, setError] = useState('');
  const [showRewardForm, setShowRewardForm] = useState(false);
  const [editingReward, setEditingReward] = useState(null);
  const [showCoinAdjust, setShowCoinAdjust] = useState(false);
  const [showExchange, setShowExchange] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  const { data: exchangeData, loading: loadingExchanges, reload: reloadExchanges } = useApi(getExchangeRequests);
  const { data: rateData } = useApi(getExchangeRate);

  const loading = loadingRewards || loadingRedemptions || loadingBalance || loadingExchanges;

  const refresh = () => {
    reloadRewards();
    reloadRedemptions();
    reloadBalance();
    reloadExchanges();
  };

  const handleRedeem = async (reward) => {
    setError('');
    try {
      await redeemReward(reward.id);
      refresh();
    } catch (e) { setError(e.message); }
  };

  const handleApprove = async (id) => { await approveRedemption(id); refresh(); };
  const handleDeny = async (id) => { await denyRedemption(id); refresh(); };
  const handleExchangeApprove = async (id) => { await approveExchange(id); refresh(); };
  const handleExchangeDeny = async (id) => { await denyExchange(id); refresh(); };

  const handleDelete = async (id) => {
    try {
      await deleteReward(id);
      setDeleteConfirm(null);
      refresh();
    } catch (e) { setError(e.message); }
  };

  if (loading) return <Loader />;

  const rewards = normalizeList(rewardsData);
  const redemptions = normalizeList(redemptionsData);
  const coinBalance = balanceData?.balance ?? 0;
  const pending = redemptions.filter((r) => r.status === 'pending');
  const exchanges = normalizeList(exchangeData);
  const pendingExchanges = exchanges.filter((e) => e.status === 'pending');
  const exchangeRate = rateData?.coins_per_dollar;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-heading text-2xl font-bold">Reward Shop</h1>
        {isParent && (
          <div className="flex gap-2">
            <button
              onClick={() => setShowCoinAdjust(true)}
              className="flex items-center gap-1 bg-forge-muted hover:bg-forge-border text-forge-text text-xs px-3 py-1.5 rounded-lg border border-forge-border"
            >
              <Coins size={14} /> Adjust Coins
            </button>
            <button
              onClick={() => { setEditingReward(null); setShowRewardForm(true); }}
              className="flex items-center gap-1 bg-amber-primary hover:bg-amber-highlight text-black text-xs font-semibold px-3 py-1.5 rounded-lg"
            >
              <Plus size={14} /> New Reward
            </button>
          </div>
        )}
      </div>

      <ErrorAlert message={error} />

      <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
        <Card className="text-center py-5">
          <div className="text-xs text-forge-text-dim mb-1 flex items-center justify-center gap-1">
            <Coins size={14} /> Coin Balance
          </div>
          <div className="font-heading text-4xl font-bold text-amber-highlight">
            {coinBalance}
          </div>
          {!isParent && (
            <button
              onClick={() => setShowExchange(true)}
              className="mt-3 inline-flex items-center gap-1.5 bg-amber-primary/20 hover:bg-amber-primary/30 text-amber-highlight text-xs font-semibold px-4 py-2 rounded-lg border border-amber-primary/30"
            >
              <ArrowRightLeft size={14} /> Exchange Money for Coins
            </button>
          )}
        </Card>
      </motion.div>

      {isParent && pending.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3">Pending Approvals</h2>
          <div className="space-y-2">
            {pending.map((r) => (
              <Card key={r.id} className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">
                    {r.user_name} → {r.reward.icon} {r.reward.name}
                  </div>
                  <div className="text-xs text-forge-text-dim">
                    {r.coin_cost_snapshot} coins • {formatDateTime(r.requested_at)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleApprove(r.id)}
                    className="flex items-center gap-1 bg-green-500/20 hover:bg-green-500/30 text-green-300 text-xs px-3 py-1.5 rounded-lg border border-green-500/30"
                  >
                    <Check size={14} /> Approve
                  </button>
                  <button
                    onClick={() => handleDeny(r.id)}
                    className="flex items-center gap-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs px-3 py-1.5 rounded-lg border border-red-500/30"
                  >
                    <X size={14} /> Deny
                  </button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {isParent && pendingExchanges.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <ArrowRightLeft size={18} /> Pending Exchanges
          </h2>
          <div className="space-y-2">
            {pendingExchanges.map((ex) => (
              <Card key={ex.id} className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">
                    {ex.user_name} — ${Number(ex.dollar_amount).toFixed(2)} → {ex.coin_amount} coins
                  </div>
                  <div className="text-xs text-forge-text-dim">
                    Rate: {ex.exchange_rate} coins/$1 • {formatDateTime(ex.created_at)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleExchangeApprove(ex.id)}
                    className="flex items-center gap-1 bg-green-500/20 hover:bg-green-500/30 text-green-300 text-xs px-3 py-1.5 rounded-lg border border-green-500/30"
                  >
                    <Check size={14} /> Approve
                  </button>
                  <button
                    onClick={() => handleExchangeDeny(ex.id)}
                    className="flex items-center gap-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs px-3 py-1.5 rounded-lg border border-red-500/30"
                  >
                    <X size={14} /> Deny
                  </button>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div>
        <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
          <Gift size={18} /> Shop
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {rewards.map((r) => {
            const affordable = coinBalance >= r.cost_coins;
            const outOfStock = r.stock !== null && r.stock !== undefined && r.stock <= 0;
            return (
              <Card key={r.id} className={`${RARITY_COLORS[r.rarity]} flex flex-col relative`}>
                {isParent && (
                  <div className="absolute top-2 right-2 flex gap-1">
                    <button
                      onClick={() => { setEditingReward(r); setShowRewardForm(true); }}
                      className="p-1 bg-forge-bg/80 hover:bg-forge-muted rounded text-forge-text-dim hover:text-forge-text"
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      onClick={() => setDeleteConfirm(r.id)}
                      className="p-1 bg-forge-bg/80 hover:bg-red-500/30 rounded text-forge-text-dim hover:text-red-300"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
                {isParent && !r.is_active && (
                  <div className="text-[10px] text-red-400 text-center mb-1">Inactive</div>
                )}
                <div className="text-3xl mb-1 text-center">{r.icon || '🎁'}</div>
                <div className="text-sm font-medium text-center">{r.name}</div>
                {r.description && (
                  <div className="text-xs text-forge-text-dim text-center mt-1 line-clamp-2">
                    {r.description}
                  </div>
                )}
                <div className="flex items-center justify-center gap-1 mt-2 text-amber-highlight font-heading font-bold">
                  <Coins size={12} /> {r.cost_coins}
                </div>
                {r.stock !== null && r.stock !== undefined && (
                  <div className="text-xs text-forge-text-dim text-center">
                    {r.stock} left
                  </div>
                )}
                {!isParent && (
                  <button
                    disabled={!affordable || outOfStock}
                    onClick={() => handleRedeem(r)}
                    className="mt-2 w-full bg-amber-primary hover:bg-amber-highlight disabled:opacity-30 disabled:cursor-not-allowed text-black text-xs font-semibold py-1.5 rounded-lg"
                  >
                    {outOfStock ? 'Out of stock' : affordable ? 'Redeem' : 'Not enough'}
                  </button>
                )}
              </Card>
            );
          })}
        </div>
      </div>

      {redemptions.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <Clock size={18} /> {isParent ? 'All Redemptions' : 'My Redemptions'}
          </h2>
          <div className="space-y-2">
            {redemptions.map((r) => (
              <Card key={r.id} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="text-xl">{r.reward.icon || '🎁'}</div>
                  <div>
                    <div className="text-sm font-medium">{r.reward.name}</div>
                    <div className="text-xs text-forge-text-dim">
                      {isParent && `${r.user_name} • `}
                      {formatDate(r.requested_at)} • {r.coin_cost_snapshot} coins
                    </div>
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[r.status] || STATUS_COLORS.pending}`}>
                  {r.status}
                </span>
              </Card>
            ))}
          </div>
        </div>
      )}

      {exchanges.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <ArrowRightLeft size={18} /> {isParent ? 'All Exchanges' : 'My Exchanges'}
          </h2>
          <div className="space-y-2">
            {exchanges.map((ex) => (
              <Card key={ex.id} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-amber-primary/20 flex items-center justify-center">
                    <ArrowRightLeft size={14} className="text-amber-highlight" />
                  </div>
                  <div>
                    <div className="text-sm font-medium">
                      ${Number(ex.dollar_amount).toFixed(2)} → {ex.coin_amount} coins
                    </div>
                    <div className="text-xs text-forge-text-dim">
                      {isParent && `${ex.user_name} • `}
                      {formatDate(ex.created_at)} • {ex.exchange_rate} coins/$1
                    </div>
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[ex.status] || STATUS_COLORS.pending}`}>
                  {ex.status}
                </span>
              </Card>
            ))}
          </div>
        </div>
      )}

      {showRewardForm && (
        <RewardFormModal
          reward={editingReward}
          onClose={() => setShowRewardForm(false)}
          onSaved={() => { setShowRewardForm(false); refresh(); }}
        />
      )}

      {showCoinAdjust && (
        <CoinAdjustModal
          onClose={() => setShowCoinAdjust(false)}
          onSaved={() => { setShowCoinAdjust(false); refresh(); }}
        />
      )}

      {showExchange && (
        <CoinExchangeModal
          exchangeRate={exchangeRate}
          onClose={() => setShowExchange(false)}
          onSaved={() => { setShowExchange(false); refresh(); }}
        />
      )}

      {deleteConfirm && (
        <AnimatePresence>
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          >
            <div className="absolute inset-0 bg-black/60" onClick={() => setDeleteConfirm(null)} />
            <motion.div
              className="relative bg-forge-card border border-forge-border rounded-2xl p-5 max-w-sm w-full mx-4"
              initial={{ scale: 0.9 }} animate={{ scale: 1 }}
            >
              <h3 className="font-heading font-bold mb-2">Delete Reward?</h3>
              <p className="text-sm text-forge-text-dim mb-4">This cannot be undone. Existing redemptions will be preserved.</p>
              <div className="flex justify-end gap-2">
                <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 text-sm text-forge-text-dim hover:text-forge-text">Cancel</button>
                <button
                  onClick={() => handleDelete(deleteConfirm)}
                  className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-sm font-semibold rounded-lg border border-red-500/30"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
        </AnimatePresence>
      )}
    </div>
  );
}

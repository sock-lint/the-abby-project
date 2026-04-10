import { useState } from 'react';
import { motion } from 'framer-motion';
import { Coins, Check, X, Clock, Gift } from 'lucide-react';
import {
  getRewards, redeemReward, getRedemptions, getCoinBalance,
  approveRedemption, denyRedemption,
} from '../api';
import { useApi, useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import { RARITY_COLORS, STATUS_COLORS } from '../constants/colors';
import { formatDate, formatDateTime } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function Rewards() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';

  const { data: rewardsData, loading: loadingRewards, reload: reloadRewards } = useApi(getRewards);
  const { data: redemptionsData, loading: loadingRedemptions, reload: reloadRedemptions } = useApi(getRedemptions);
  const { data: balanceData, loading: loadingBalance, reload: reloadBalance } = useApi(getCoinBalance);
  const [error, setError] = useState('');

  const loading = loadingRewards || loadingRedemptions || loadingBalance;

  const refresh = () => {
    reloadRewards();
    reloadRedemptions();
    reloadBalance();
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

  if (loading) return <Loader />;

  const rewards = normalizeList(rewardsData);
  const redemptions = normalizeList(redemptionsData);
  const coinBalance = balanceData?.balance ?? 0;
  const pending = redemptions.filter((r) => r.status === 'pending');

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Reward Shop</h1>

      <ErrorAlert message={error} />

      <motion.div initial={{ scale: 0.95, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
        <Card className="text-center py-5">
          <div className="text-xs text-forge-text-dim mb-1 flex items-center justify-center gap-1">
            <Coins size={14} /> Coin Balance
          </div>
          <div className="font-heading text-4xl font-bold text-amber-highlight">
            {coinBalance}
          </div>
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

      <div>
        <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
          <Gift size={18} /> Shop
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {rewards.map((r) => {
            const affordable = coinBalance >= r.cost_coins;
            const outOfStock = r.stock !== null && r.stock !== undefined && r.stock <= 0;
            return (
              <Card key={r.id} className={`${RARITY_COLORS[r.rarity]} flex flex-col`}>
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
    </div>
  );
}

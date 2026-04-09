import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Coins, Check, X, Clock, Gift } from 'lucide-react';
import {
  getRewards, redeemReward, getRedemptions, getCoinBalance,
  approveRedemption, denyRedemption,
} from '../api';
import { useAuth } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';

const rarityColors = {
  common: 'border-rarity-common/30 bg-rarity-common/5',
  uncommon: 'border-rarity-uncommon/30 bg-rarity-uncommon/5',
  rare: 'border-rarity-rare/30 bg-rarity-rare/5',
  epic: 'border-rarity-epic/30 bg-rarity-epic/5',
  legendary: 'border-rarity-legendary/30 bg-rarity-legendary/5',
};

const statusStyles = {
  pending: 'bg-yellow-400/10 text-yellow-300 border-yellow-400/30',
  approved: 'bg-blue-400/10 text-blue-300 border-blue-400/30',
  fulfilled: 'bg-green-400/10 text-green-300 border-green-400/30',
  denied: 'bg-red-400/10 text-red-300 border-red-400/30',
  canceled: 'bg-gray-400/10 text-gray-300 border-gray-400/30',
};

export default function Rewards() {
  const { user } = useAuth();
  const isParent = user?.role === 'parent';

  const [rewards, setRewards] = useState([]);
  const [redemptions, setRedemptions] = useState([]);
  const [balance, setBalance] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = async () => {
    setLoading(true);
    try {
      const [r, red, bal] = await Promise.all([
        getRewards(), getRedemptions(), getCoinBalance(),
      ]);
      setRewards(r?.results || r || []);
      setRedemptions(red?.results || red || []);
      setBalance(bal);
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  useEffect(() => { refresh(); }, []);

  const handleRedeem = async (reward) => {
    setError('');
    try {
      await redeemReward(reward.id);
      await refresh();
    } catch (e) { setError(e.message); }
  };

  const handleApprove = async (id) => { await approveRedemption(id); await refresh(); };
  const handleDeny = async (id) => { await denyRedemption(id); await refresh(); };

  if (loading) return <Loader />;

  const coinBalance = balance?.balance ?? 0;
  const pending = redemptions.filter((r) => r.status === 'pending');

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Reward Shop</h1>

      {error && (
        <Card className="border-red-400/30 bg-red-400/5 text-red-300 text-sm">{error}</Card>
      )}

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
                    {r.coin_cost_snapshot} coins • {new Date(r.requested_at).toLocaleString()}
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
              <Card key={r.id} className={`${rarityColors[r.rarity]} flex flex-col`}>
                <div className="text-3xl mb-1 text-center">{r.icon || '🎁'}</div>
                <div className="text-sm font-medium text-center">{r.name}</div>
                {r.description && (
                  <div className="text-[10px] text-forge-text-dim text-center mt-1 line-clamp-2">
                    {r.description}
                  </div>
                )}
                <div className="flex items-center justify-center gap-1 mt-2 text-amber-highlight font-heading font-bold">
                  <Coins size={12} /> {r.cost_coins}
                </div>
                {r.stock !== null && r.stock !== undefined && (
                  <div className="text-[10px] text-forge-text-dim text-center">
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
                    <div className="text-[11px] text-forge-text-dim">
                      {isParent && `${r.user_name} • `}
                      {new Date(r.requested_at).toLocaleDateString()} • {r.coin_cost_snapshot} coins
                    </div>
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${statusStyles[r.status] || statusStyles.pending}`}>
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

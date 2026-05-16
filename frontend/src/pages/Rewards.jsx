import { useState } from 'react';
import { Coins, Plus } from 'lucide-react';
import {
  approveExchange, approveRedemption, rejectExchange, rejectRedemption,
  deleteReward, getCoinBalance, getExchangeRate, getExchangeRequests,
  getRedemptions, getRewards, redeemReward,
  addRewardToWishlist, removeRewardFromWishlist,
} from '../api';
import CatalogSearch from '../components/CatalogSearch';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { useApi } from '../hooks/useApi';
import { useConfirmState } from '../hooks/useConfirmState';
import { useRole } from '../hooks/useRole';
import Button from '../components/Button';
import { normalizeList } from '../utils/api';
import CoinAdjustModal from './rewards/CoinAdjustModal';
import CoinBalanceCard from './rewards/CoinBalanceCard';
import CoinExchangeModal from './rewards/CoinExchangeModal';
import ExchangeApprovalQueue from './rewards/ExchangeApprovalQueue';
import ExchangeHistory from './rewards/ExchangeHistory';
import RedemptionApprovalQueue from './rewards/RedemptionApprovalQueue';
import RedemptionHistory from './rewards/RedemptionHistory';
import RewardFormModal from './rewards/RewardFormModal';
import RewardShop from './rewards/RewardShop';

export default function Rewards() {
  const { isParent } = useRole();
  const {
    data: rewardsData, loading: loadingRewards, reload: reloadRewards,
    setData: setRewardsData,
  } = useApi(getRewards);
  const { data: redemptionsData, loading: loadingRedemptions, reload: reloadRedemptions } = useApi(getRedemptions);
  const { data: balanceData, loading: loadingBalance, reload: reloadBalance } = useApi(getCoinBalance);
  const { data: exchangeData, loading: loadingExchanges, reload: reloadExchanges } = useApi(getExchangeRequests);
  const { data: rateData } = useApi(getExchangeRate);

  const [error, setError] = useState('');
  const [showRewardForm, setShowRewardForm] = useState(false);
  const [editingReward, setEditingReward] = useState(null);
  const [showCoinAdjust, setShowCoinAdjust] = useState(false);
  const [showExchange, setShowExchange] = useState(false);
  const [outOfStock, setOutOfStock] = useState(null);
  const [shopFilter, setShopFilter] = useState('');
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  const refresh = () => {
    reloadRewards(); reloadRedemptions(); reloadBalance(); reloadExchanges();
  };

  const handleRedeem = async (reward) => {
    setError('');
    // Pre-flight check: if the cached balance is short, render a
    // concrete delta ("you need 12 more coins") rather than waiting on
    // a generic 4xx string. Backend re-validates on submit so this is
    // safe even if the cached balance is stale.
    const balance = balanceData?.balance ?? 0;
    if (reward.cost > balance) {
      const short = reward.cost - balance;
      setError(
        `Not enough coins yet — need ${short} more (cost: ${reward.cost}, you have ${balance}).`,
      );
      return;
    }
    try {
      await redeemReward(reward.id);
      refresh();
    } catch (e) {
      // 409 with code:"out_of_stock" → degrade to a friendly modal that
      // offers similar rewards + a "notify me" toggle, instead of just
      // bouncing an error toast that leaves the kid stranded.
      if (e?.status === 409 && e.response?.code === 'out_of_stock') {
        setOutOfStock({ reward, similar: e.response.similar || [] });
        return;
      }
      setError(e.message);
    }
  };

  const handleToggleWishlist = async (reward) => {
    setError('');
    const newState = !reward.on_my_wishlist;
    // Optimistic flip — keeps the bookmark snappy on slow networks.
    // Backend reconciliation happens on the next page-level refresh
    // (redeem, etc.). Wishlist state is cheap to recover on error.
    const patchList = (prev, value) => {
      if (!prev) return prev;
      const list = Array.isArray(prev) ? prev : prev.results || [];
      const updated = list.map((r) =>
        r.id === reward.id ? { ...r, on_my_wishlist: value } : r,
      );
      return Array.isArray(prev) ? updated : { ...prev, results: updated };
    };
    setRewardsData((prev) => patchList(prev, newState));
    try {
      if (newState) {
        await addRewardToWishlist(reward.id);
      } else {
        await removeRewardFromWishlist(reward.id);
      }
    } catch (e) {
      // Rollback to the prior state.
      setRewardsData((prev) => patchList(prev, !newState));
      setError(e.message);
    }
  };

  const handleApprove = async (id) => { await approveRedemption(id); refresh(); };
  const handleReject = async (id) => { await rejectRedemption(id); refresh(); };
  const handleExchangeApprove = async (id) => { await approveExchange(id); refresh(); };
  const handleExchangeReject = async (id) => { await rejectExchange(id); refresh(); };

  const handleEditReward = (reward) => {
    setEditingReward(reward);
    setShowRewardForm(true);
  };

  const handleDeleteReward = (id) =>
    askConfirm({
      title: 'Delete Reward?',
      message: 'This cannot be undone. Existing redemptions will be preserved.',
      onConfirm: async () => {
        try {
          await deleteReward(id);
          refresh();
        } catch (e) { setError(e.message); }
      },
    });

  if (loadingRewards || loadingRedemptions || loadingBalance || loadingExchanges) {
    return <Loader />;
  }

  const rewards = normalizeList(rewardsData);
  const redemptions = normalizeList(redemptionsData);
  const exchanges = normalizeList(exchangeData);
  const coinBalance = balanceData?.balance ?? 0;
  const pending = redemptions.filter((r) => r.status === 'pending');
  const pendingExchanges = exchanges.filter((e) => e.status === 'pending');
  const exchangeRate = rateData?.coins_per_dollar;
  const shopQ = shopFilter.trim().toLowerCase();
  const filteredRewards = shopQ
    ? rewards.filter((r) =>
        (r.name || '').toLowerCase().includes(shopQ)
        || (r.description || '').toLowerCase().includes(shopQ),
      )
    : rewards;

  return (
    <div className="space-y-6">
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the bazaar · barter coins for treasures
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Bazaar
          </h1>
          <div className="font-script text-body text-ink-whisper mt-1 max-w-xl">
            barter coins earned from work, duties, rituals, and badges · some treasures need a parent's nod first
          </div>
        </div>
        {isParent && (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCoinAdjust(true)}
              className="flex items-center gap-1"
            >
              <Coins size={14} /> Adjust Coins
            </Button>
            <Button
              size="sm"
              onClick={() => { setEditingReward(null); setShowRewardForm(true); }}
              className="flex items-center gap-1"
            >
              <Plus size={14} /> New Reward
            </Button>
          </div>
        )}
      </header>

      <ErrorAlert message={error} />

      <CoinBalanceCard
        coinBalance={coinBalance}
        isParent={isParent}
        onOpenExchange={() => setShowExchange(true)}
      />

      {isParent && (
        <RedemptionApprovalQueue
          pending={pending}
          onApprove={handleApprove}
          onReject={handleReject}
        />
      )}

      {isParent && (
        <ExchangeApprovalQueue
          pending={pendingExchanges}
          onApprove={handleExchangeApprove}
          onReject={handleExchangeReject}
        />
      )}

      {rewards.length > 0 && (
        <CatalogSearch
          value={shopFilter}
          onChange={setShopFilter}
          placeholder="Search the bazaar…"
          ariaLabel="Filter rewards"
        />
      )}

      <RewardShop
        rewards={filteredRewards}
        isParent={isParent}
        coinBalance={coinBalance}
        onRedeem={handleRedeem}
        onEdit={handleEditReward}
        onDelete={handleDeleteReward}
        onToggleWishlist={isParent ? undefined : handleToggleWishlist}
      />

      <RedemptionHistory redemptions={redemptions} isParent={isParent} />
      <ExchangeHistory exchanges={exchanges} isParent={isParent} />

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

      {confirmState && (
        <ConfirmDialog
          title={confirmState.title}
          message={confirmState.message}
          confirmLabel={confirmState.confirmLabel}
          onConfirm={async () => {
            const fn = confirmState.onConfirm;
            closeConfirm();
            await fn();
          }}
          onCancel={closeConfirm}
        />
      )}

      {outOfStock && (
        <OutOfStockSheet
          state={outOfStock}
          onClose={() => setOutOfStock(null)}
          onWishlist={async () => {
            try {
              await addRewardToWishlist(outOfStock.reward.id);
              await reloadRewards();
              setOutOfStock(null);
            } catch (e) { setError(e.message); }
          }}
          onPickSimilar={async (similar) => {
            setOutOfStock(null);
            await handleRedeem(similar);
          }}
        />
      )}
    </div>
  );
}

function OutOfStockSheet({ state, onClose, onWishlist, onPickSimilar }) {
  const { reward, similar } = state;
  return (
    <div
      role="dialog"
      aria-labelledby="oos-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/60 p-4"
      onClick={onClose}
    >
      <div
        className="bg-ink-page rounded-lg shadow-xl max-w-md w-full p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="oos-title" className="font-display text-xl text-ink-primary">
          {reward.icon} {reward.name} — sold out
        </h2>
        <p className="font-body text-body text-ink-secondary">
          This one's been claimed for now. Want a heads-up when it's back?
        </p>
        <Button onClick={onWishlist} variant="primary" size="sm" className="w-full">
          Notify me when restocked
        </Button>
        {similar.length > 0 && (
          <div>
            <div className="font-script text-body text-sheikah-teal-deep mt-2 mb-1.5">
              you might also like
            </div>
            <div className="space-y-1.5">
              {similar.map((s) => (
                <Button
                  key={s.id}
                  variant="secondary"
                  size="sm"
                  onClick={() => onPickSimilar(s)}
                  className="w-full text-left flex items-center justify-between gap-2"
                >
                  <span className="font-body text-body text-ink-primary truncate">
                    {s.icon} {s.name}
                  </span>
                  <span className="font-script text-tiny text-gold-leaf shrink-0">
                    {s.cost_coins}c
                  </span>
                </Button>
              ))}
            </div>
          </div>
        )}
        <Button onClick={onClose} variant="ghost" size="sm" className="w-full">
          Close
        </Button>
      </div>
    </div>
  );
}

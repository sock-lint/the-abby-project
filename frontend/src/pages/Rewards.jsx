import { useState } from 'react';
import { Coins, Plus } from 'lucide-react';
import {
  approveExchange, approveRedemption, rejectExchange, rejectRedemption,
  deleteReward, getCoinBalance, getExchangeRate, getExchangeRequests,
  getRedemptions, getRewards, redeemReward,
} from '../api';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import { useApi } from '../hooks/useApi';
import { useConfirmState } from '../hooks/useConfirmState';
import { useRole } from '../hooks/useRole';
import { buttonPrimary } from '../constants/styles';
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
  const { data: rewardsData, loading: loadingRewards, reload: reloadRewards } = useApi(getRewards);
  const { data: redemptionsData, loading: loadingRedemptions, reload: reloadRedemptions } = useApi(getRedemptions);
  const { data: balanceData, loading: loadingBalance, reload: reloadBalance } = useApi(getCoinBalance);
  const { data: exchangeData, loading: loadingExchanges, reload: reloadExchanges } = useApi(getExchangeRequests);
  const { data: rateData } = useApi(getExchangeRate);

  const [error, setError] = useState('');
  const [showRewardForm, setShowRewardForm] = useState(false);
  const [editingReward, setEditingReward] = useState(null);
  const [showCoinAdjust, setShowCoinAdjust] = useState(false);
  const [showExchange, setShowExchange] = useState(false);
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  const refresh = () => {
    reloadRewards(); reloadRedemptions(); reloadBalance(); reloadExchanges();
  };

  const handleRedeem = async (reward) => {
    setError('');
    try {
      await redeemReward(reward.id);
      refresh();
    } catch (e) { setError(e.message); }
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
              className={`flex items-center gap-1 px-3 py-1.5 text-xs ${buttonPrimary}`}
            >
              <Plus size={14} /> New Reward
            </button>
          </div>
        )}
      </div>

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

      <RewardShop
        rewards={rewards}
        isParent={isParent}
        coinBalance={coinBalance}
        onRedeem={handleRedeem}
        onEdit={handleEditReward}
        onDelete={handleDeleteReward}
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
    </div>
  );
}

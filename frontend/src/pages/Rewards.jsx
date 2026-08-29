import { useCallback, useState } from 'react';
import useSearchParamState from '../hooks/useSearchParamState';
import { Coins, Plus } from 'lucide-react';
import {
  approveExchange, approveRedemption, rejectExchange, rejectRedemption,
  deleteReward, getCoinBalance, getExchangeRate, getExchangeRequests,
  getRedemptions, getRewards, redeemReward,
  addRewardToWishlist, removeRewardFromWishlist,
} from '../api';
import { hapticSuccess } from '../utils/haptics';
import AccordionSection from '../components/dashboard/AccordionSection';
import BottomSheet from '../components/BottomSheet';
import CatalogSearch from '../components/CatalogSearch';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import PageShell from '../components/layout/PageShell';
import SectionHeader from '../components/SectionHeader';
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
  // Every fetch here surfaces its own error + retry. A swallowed balance
  // fetch used to paint a confident gold "0" over the kid's real coins, and
  // a swallowed shop fetch read as "no rewards yet — ask a parent".
  const {
    data: rewardsData, loading: loadingRewards, error: rewardsError,
    reload: reloadRewards, setData: setRewardsData,
  } = useApi(getRewards);
  const {
    data: redemptionsData, loading: loadingRedemptions,
    error: redemptionsError, reload: reloadRedemptions,
  } = useApi(getRedemptions);
  const {
    data: balanceData, loading: loadingBalance, error: balanceError,
    reload: reloadBalance,
  } = useApi(getCoinBalance);
  const {
    data: exchangeData, loading: loadingExchanges, error: exchangesError,
    reload: reloadExchanges,
  } = useApi(getExchangeRequests);
  const { data: rateData, error: rateError, reload: reloadRate } = useApi(getExchangeRate);

  const [error, setError] = useState('');
  const [pendingId, setPendingId] = useState(null);
  const [showRewardForm, setShowRewardForm] = useState(false);
  const [editingReward, setEditingReward] = useState(null);
  const [showExchange, setShowExchange] = useState(false);
  const [outOfStock, setOutOfStock] = useState(null);
  const [confirmRedeem, setConfirmRedeem] = useState(null);
  const [shopFilter, setShopFilter] = useSearchParamState('q', '');
  const [adjustParam, setAdjustParam] = useSearchParamState('adjust', '');
  // ?adjust=1 opens the coin adjuster straight from the quick-actions FAB
  // and the dashboard's Quick adjusts row (same shape as ?new=1 on Forge).
  const [showCoinAdjust, setShowCoinAdjust] = useState(adjustParam === '1');
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  // Drop ?adjust=1 as the sheet closes so a tab switch back here (ChapterHub
  // remounts tab bodies) doesn't re-open it.
  const closeCoinAdjust = useCallback(() => {
    setShowCoinAdjust(false);
    setAdjustParam('');
  }, [setAdjustParam]);

  const refresh = () => {
    reloadRewards(); reloadRedemptions(); reloadBalance(); reloadExchanges();
  };


  // Tapping Barter opens a confirm step rather than spending immediately —
  // coins are held the moment the request posts and a kid can't cancel it.
  const handleRedeem = (reward) => {
    setError('');
    setConfirmRedeem(reward);
  };

  const performRedeem = async (reward) => {
    setError('');
    setConfirmRedeem(null);
    const balance = coinBalance;
    const cost = reward.cost_coins ?? 0;
    // balance === null means the fetch failed — skip the client-side
    // shortfall guard rather than telling the kid they're short by a number
    // we don't actually know. The server still enforces the real balance.
    if (balance !== null && cost > balance) {
      const short = cost - balance;
      setError(
        `Not enough coins yet — need ${short} more (cost: ${cost}, you have ${balance}).`,
      );
      return;
    }
    setPendingId(reward.id);
    try {
      await redeemReward(reward.id);
      hapticSuccess();
      refresh();
    } catch (e) {
      if (e?.status === 409 && e.response?.code === 'out_of_stock') {
        setOutOfStock({ reward, similar: e.response.similar || [] });
        return;
      }
      setError(e.message);
    } finally {
      setPendingId(null);
    }
  };

  const handleToggleWishlist = async (reward) => {
    setError('');
    const newState = !reward.on_my_wishlist;
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
      setRewardsData((prev) => patchList(prev, !newState));
      setError(e.message);
    }
  };

  const handleApprove = async (id) => {
    setPendingId(id);
    try { await approveRedemption(id); refresh(); }
    catch (e) { setError(e.message); }
    finally { setPendingId(null); }
  };
  const handleReject = async (id) => {
    setPendingId(id);
    try { await rejectRedemption(id); refresh(); }
    catch (e) { setError(e.message); }
    finally { setPendingId(null); }
  };
  const handleExchangeApprove = async (id) => {
    setPendingId(id);
    try { await approveExchange(id); refresh(); }
    catch (e) { setError(e.message); }
    finally { setPendingId(null); }
  };
  const handleExchangeReject = async (id) => {
    setPendingId(id);
    try { await rejectExchange(id); refresh(); }
    catch (e) { setError(e.message); }
    finally { setPendingId(null); }
  };

  const handleEditReward = (reward) => {
    setEditingReward(reward);
    setShowRewardForm(true);
  };

  const handleDeleteReward = (id) =>
    askConfirm({
      title: 'Delete reward?',
      message: 'This cannot be undone. Existing redemptions will be preserved.',
      onConfirm: async () => {
        try {
          await deleteReward(id);
          refresh();
        } catch (e) { setError(e.message); }
      },
    });

  const rewards = normalizeList(rewardsData);
  const redemptions = normalizeList(redemptionsData);
  const exchanges = normalizeList(exchangeData);
  // null = we don't know (fetch failed). Downstream treats unknown as
  // "let them try" rather than as zero.
  const coinBalance = balanceError ? null : (balanceData?.balance ?? 0);
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
    <PageShell>
      <header className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <div className="font-script text-sheikah-teal-deep text-base">
            the bazaar · barter coins for treasures
          </div>
          {/* Below md the Treasury hub's tab strip already names this page —
              the stacked h1 + explainer ate ~100px above the fold on phones. */}
          <h1 className="hidden md:block font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Bazaar
          </h1>
          <div className="hidden md:block font-script text-body text-ink-whisper mt-1 max-w-xl">
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
              <Coins size={14} /> Adjust coins
            </Button>
            <Button
              size="sm"
              onClick={() => { setEditingReward(null); setShowRewardForm(true); }}
              className="flex items-center gap-1"
            >
              <Plus size={14} /> New reward
            </Button>
          </div>
        )}
      </header>

      <ErrorAlert message={error} />

      {loadingBalance ? <Loader /> : balanceError ? (
        <ErrorAlert
          message={`Couldn't load your coin balance. ${balanceError}`}
          onRetry={reloadBalance}
        />
      ) : (
        <CoinBalanceCard
          coinBalance={coinBalance}
          isParent={isParent}
          onOpenExchange={() => setShowExchange(true)}
        />
      )}

      {/* Ungated by role: these feed the parent's pending queues AND both
          roles' history accordions, so a swallowed failure silently drops a
          whole section for a child too. */}
      {redemptionsError && (
        <ErrorAlert
          message={`Couldn't load redemptions. ${redemptionsError}`}
          onRetry={reloadRedemptions}
        />
      )}
      {exchangesError && (
        <ErrorAlert
          message={`Couldn't load exchanges. ${exchangesError}`}
          onRetry={reloadExchanges}
        />
      )}

      {isParent && (
        loadingRedemptions ? <Loader /> : pending.length > 0 && (
          <section>
            <SectionHeader index={0} title="Pending redemptions" count={pending.length} />
            <div className="mt-3">
              <RedemptionApprovalQueue
                pending={pending}
                pendingId={pendingId}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            </div>
          </section>
        )
      )}

      {isParent && (
        loadingExchanges ? <Loader /> : pendingExchanges.length > 0 && (
          <section>
            <SectionHeader index={1} title="Pending exchanges" count={pendingExchanges.length} />
            <div className="mt-3">
              <ExchangeApprovalQueue
                pending={pendingExchanges}
                pendingId={pendingId}
                onApprove={handleExchangeApprove}
                onReject={handleExchangeReject}
              />
            </div>
          </section>
        )
      )}

      <section>
        <SectionHeader
          index={isParent ? 2 : 0}
          title="Shop"
          kicker="browse the bazaar"
        />
        <div className="mt-3 space-y-4">
          {loadingRewards ? <Loader /> : rewardsError ? (
            <ErrorAlert
              message={`Couldn't load the bazaar. ${rewardsError}`}
              onRetry={reloadRewards}
            />
          ) : (
            <>
              {rewards.length > 0 && (
                <div className="space-y-1">
                  <CatalogSearch
                    value={shopFilter}
                    onChange={setShopFilter}
                    placeholder="Search the bazaar…"
                    ariaLabel="Filter rewards"
                  />
                  {shopFilter && (
                    <div className="font-script text-caption text-sheikah-teal-deep tabular-nums">
                      {filteredRewards.length} {filteredRewards.length === 1 ? 'match' : 'matches'}
                    </div>
                  )}
                </div>
              )}
              <RewardShop
                rewards={filteredRewards}
                isParent={isParent}
                coinBalance={coinBalance}
                pendingId={pendingId}
                filterQuery={shopFilter}
                onClearFilter={() => setShopFilter('')}
                onRedeem={handleRedeem}
                onEdit={handleEditReward}
                onDelete={handleDeleteReward}
                onToggleWishlist={isParent ? undefined : handleToggleWishlist}
              />
            </>
          )}
        </div>
      </section>

      {!loadingRedemptions && redemptions.length > 0 && (
        <AccordionSection index={isParent ? 3 : 1} title="Redemption history" count={redemptions.length}>
          <RedemptionHistory redemptions={redemptions} isParent={isParent} />
        </AccordionSection>
      )}

      {!loadingExchanges && exchanges.length > 0 && (
        <AccordionSection index={isParent ? 4 : 2} title="Exchange history" count={exchanges.length}>
          <ExchangeHistory exchanges={exchanges} isParent={isParent} />
        </AccordionSection>
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
          onClose={closeCoinAdjust}
          onSaved={() => { closeCoinAdjust(); refresh(); }}
        />
      )}

      {showExchange && (
        <CoinExchangeModal
          exchangeRate={exchangeRate}
          rateError={rateError}
          onRetryRate={reloadRate}
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

      {confirmRedeem && (
        <ConfirmRedeemSheet
          reward={confirmRedeem}
          balance={coinBalance}
          onClose={() => setConfirmRedeem(null)}
          onConfirm={() => performRedeem(confirmRedeem)}
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
    </PageShell>
  );
}

function ConfirmRedeemSheet({ reward, balance, onClose, onConfirm }) {
  const cost = reward.cost_coins ?? 0;
  // balance === null means the balance fetch failed — show the cost alone
  // rather than inventing a before/after sum out of a number we don't have.
  const balanceKnown = balance !== null && balance !== undefined;
  return (
    <BottomSheet title={`${reward.icon || '🎁'} ${reward.name}`} onClose={onClose}>
      <div className="space-y-3">
        <div className="text-center">
          <div className="font-rune text-3xl font-bold text-gold-leaf tabular-nums">
            {balanceKnown ? `${balance} → ${Math.max(0, balance - cost)}` : `${cost} coins`}
          </div>
          <div className="font-script text-body text-ink-whisper mt-1">
            {balanceKnown
              ? `costs ${cost} coins`
              : `costs ${cost} coins · your balance couldn't be reached just now`}
          </div>
        </div>
        <p className="font-body text-caption text-ink-secondary text-center">
          Your coins are held as soon as you ask — a parent has to approve it
          before you get the reward, and only they can hand them back.
        </p>
        <Button onClick={onConfirm} variant="primary" className="w-full">
          Yes, barter it
        </Button>
        <Button onClick={onClose} variant="ghost" size="sm" className="w-full">
          Not yet
        </Button>
      </div>
    </BottomSheet>
  );
}

function OutOfStockSheet({ state, onClose, onWishlist, onPickSimilar }) {
  const { reward, similar } = state;
  return (
    <BottomSheet
      title={`${reward.icon} ${reward.name} — sold out`}
      onClose={onClose}
    >
      <div className="space-y-3">
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
      </div>
    </BottomSheet>
  );
}

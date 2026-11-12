import { useCallback, useEffect, useRef, useState } from 'react';
import useSearchParamState from '../hooks/useSearchParamState';
import { Plus } from 'lucide-react';
import { CoinIcon } from '../components/icons/JournalIcons';
import {
  approveExchange, approveRedemption, rejectExchange, rejectRedemption,
  deleteReward, getCoinBalance, getExchangeRate, getExchangeRequests,
  getRedemptions, getRewards, redeemReward, getPendingRedemptions, getPendingExchangeRequests,
  addRewardToWishlist, removeRewardFromWishlist, getAwaitingRedemptions, deliverRedemption,
} from '../api';
import { hapticSuccess } from '../utils/haptics';
import AccordionSection from '../components/dashboard/AccordionSection';
import BottomSheet from '../components/BottomSheet';
import CatalogSearch from '../components/CatalogSearch';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorAlert from '../components/ErrorAlert';
import Loader from '../components/Loader';
import PageShell from '../components/layout/PageShell';
import ParchmentCard from '../components/journal/ParchmentCard';
import SectionHeader from '../components/SectionHeader';
import { useSpace } from '../hooks/useSpace';
import { useApi } from '../hooks/useApi';
import { useConfirmState } from '../hooks/useConfirmState';
import useChildContext from '../hooks/useChildContext';
import ChildContext from '../components/family/ChildContext';
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
import RewardDeliveryQueue from './rewards/RewardDeliveryQueue';

export default function Rewards() {
  const context = useChildContext();
  if (!context.user || context.loading) return <Loader />;
  if (context.error) return <ErrorAlert message={context.error} onRetry={context.reload} />;
  return <RewardsView key={`${context.scope}:${context.targetUserId ?? ''}`} context={context} />;
}

function RewardsView({ context }) {
  const { isParent, selectedChild, targetUserId } = context;
  const { isParentAccount, isPersonalSpace } = useSpace();
  const personalParent = isParentAccount && isPersonalSpace;
  const childName = selectedChild?.display_name || selectedChild?.first_name || selectedChild?.username;
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
  } = useApi(() => isParent && !targetUserId ? Promise.resolve(null) : getCoinBalance(isParent ? { user_id: targetUserId } : undefined), [isParent, targetUserId]);
  const {
    data: exchangeData, loading: loadingExchanges, error: exchangesError,
    reload: reloadExchanges,
  } = useApi(() => personalParent ? Promise.resolve([]) : getExchangeRequests(), [personalParent]);
  const {
    data: pendingRedemptionsData, loading: loadingPendingRedemptions,
    error: pendingRedemptionsError, reload: reloadPendingRedemptions,
  } = useApi(() => isParent ? getPendingRedemptions() : Promise.resolve([]), [isParent]);
  const {
    data: pendingExchangesData, loading: loadingPendingExchanges,
    error: pendingExchangesError, reload: reloadPendingExchanges,
  } = useApi(() => isParent ? getPendingExchangeRequests() : Promise.resolve([]), [isParent]);
  const {
    data: awaitingData, loading: loadingAwaiting, error: awaitingError, reload: reloadAwaiting,
  } = useApi(() => isParent ? getAwaitingRedemptions() : Promise.resolve([]), [isParent]);
  const { data: rateData, error: rateError, reload: reloadRate } = useApi(() => personalParent ? Promise.resolve(null) : getExchangeRate(), [personalParent]);

  const [error, setError] = useState('');
  const [pendingId, setPendingId] = useState(null);
  const [showRewardForm, setShowRewardForm] = useState(false);
  const [editingReward, setEditingReward] = useState(null);
  const [showExchange, setShowExchange] = useState(false);
  const [outOfStock, setOutOfStock] = useState(null);
  const [confirmRedeem, setConfirmRedeem] = useState(null);
  const [redemptionReceipt, setRedemptionReceipt] = useState(null);
  const [deliveredReceipts, setDeliveredReceipts] = useState({});
  const [deliveryNotice, setDeliveryNotice] = useState('');
  const [showRequestHistory, setShowRequestHistory] = useState(false);
  const receiptRef = useRef(null);
  const [shopFilter, setShopFilter] = useSearchParamState('q', '');
  const [adjustParam, setAdjustParam] = useSearchParamState('adjust', '');
  // ?adjust=1 opens the coin adjuster straight from the quick-actions FAB
  // and the dashboard's Quick adjusts row (same shape as ?new=1 on Forge).
  const [showCoinAdjust, setShowCoinAdjust] = useState(adjustParam === '1');
  const { confirmState, askConfirm, closeConfirm } = useConfirmState();

  useEffect(() => {
    // The shop can be a long grid. Bring the saved result into view when its
    // confirmation sheet closes, without animating or moving keyboard focus.
    if (redemptionReceipt) receiptRef.current?.scrollIntoView({ block: 'nearest' });
  }, [redemptionReceipt]);

  // Drop ?adjust=1 as the sheet closes so a tab switch back here (ChapterHub
  // remounts tab bodies) doesn't re-open it.
  const closeCoinAdjust = useCallback(() => {
    setShowCoinAdjust(false);
    setAdjustParam('');
  }, [setAdjustParam]);

  const refresh = () => {
    reloadRewards(); reloadRedemptions(); reloadBalance(); reloadExchanges();
    reloadPendingRedemptions(); reloadPendingExchanges();
    reloadAwaiting();
  };


  // Tapping Barter opens a confirm step rather than spending immediately —
  // coins are held the moment the request posts and a kid can't cancel it.
  const handleRedeem = (reward) => {
    setError('');
    setRedemptionReceipt(null);
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
      const redemption = await redeemReward(reward.id);
      setRedemptionReceipt({ ...redemption, reward: redemption?.reward || reward });
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
  const handleDeliver = async (id) => {
    const receipt = await deliverRedemption(id);
    setDeliveredReceipts((previous) => ({ ...previous, [id]: receipt }));
    setDeliveryNotice(`Delivery confirmed for ${receipt.reward.name}.`);
    refresh();
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
      message: 'This cannot be undone. Existing reward requests will be preserved.',
      onConfirm: async () => {
        try {
          await deleteReward(id);
          refresh();
        } catch (e) { setError(e.message); }
      },
    });

  const rewards = normalizeList(rewardsData);
  const redemptions = normalizeList(redemptionsData).map((row) => deliveredReceipts[row.id] || row);
  // The POST receipt survives a failed follow-up read. If history has a newer
  // decision for the same request, present that server-confirmed state instead.
  const currentReceipt = redemptionReceipt && (
    redemptions.find((r) => r.id === redemptionReceipt.id) || redemptionReceipt
  );
  const receiptHistory = currentReceipt?.id && !redemptions.some((r) => r.id === currentReceipt.id)
    ? [currentReceipt, ...redemptions]
    : redemptions;
  const exchanges = normalizeList(exchangeData);
  // null = we don't know (fetch failed). Downstream treats unknown as
  // "let them try" rather than as zero.
  const coinBalance = balanceError ? null : (balanceData?.balance ?? 0);
  const pending = normalizeList(pendingRedemptionsData).filter((r) => r.status === 'pending');
  const pendingExchanges = normalizeList(pendingExchangesData).filter((e) => e.status === 'pending');
  const awaiting = normalizeList(awaitingData).filter((row) => row.status === 'approved'
    && ['real_world', 'both'].includes(row.reward.fulfillment_kind) && !deliveredReceipts[row.id]);
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
            {isParent ? 'Manage rewards for your family' : 'Use your coins for rewards'}
          </div>
          {/* Below md the Treasury hub's tab strip already names this page —
              the stacked h1 + explainer ate ~100px above the fold on phones. */}
          <h1 className="sr-only md:not-sr-only font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
            Rewards
          </h1>
          <div className="hidden md:block font-script text-body text-ink-whisper mt-1 max-w-xl">
            {isParent ? 'Review requests, deliver approved rewards, and keep the family shop up to date.' : 'Use earned coins for rewards. Some rewards need parent approval.'}
          </div>
        </div>
        {isParent && (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowCoinAdjust(true)}
              className="flex items-center gap-1"
            >
              <CoinIcon size={14} /> Adjust coins
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
      {isParent && <ChildContext children={context.children} selectedChildId={targetUserId} onSelect={context.selectChild} />}
      {isParent && <p className="text-caption text-ink-secondary">{childName ? `Viewing ${childName}'s coin balance. ` : 'Add a child in Manage family to view their coin balance. '}Approval and delivery queues cover your whole family.</p>}

      {currentReceipt && (
        <ParchmentCard ref={receiptRef} className="border-moss/40 space-y-3">
          <div role="status" aria-label="Reward request update" aria-atomic="true" className="space-y-2">
            <h2 className="font-body text-lede font-semibold text-moss">
              {currentReceipt.status === 'pending'
                ? 'Request sent — awaiting parent approval'
                : currentReceipt.status === 'approved'
                  ? 'Approved — awaiting real-world delivery'
                : currentReceipt.status === 'fulfilled'
                  ? 'Reward received'
                  : currentReceipt.status === 'denied'
                    ? 'Reward request declined'
                    : 'Reward request sent'}
            </h2>
            <p className="font-body text-body font-semibold break-words">{currentReceipt.reward.name}</p>
            {currentReceipt.coin_cost_snapshot != null && (
              <p className="font-body text-body text-ink-secondary">
                {currentReceipt.coin_cost_snapshot} coins {currentReceipt.status === 'pending'
                  ? 'held for this request. Rejected requests return your coins.'
                  : ['fulfilled', 'approved'].includes(currentReceipt.status)
                    ? 'spent on this reward.'
                    : currentReceipt.status === 'denied'
                      ? 'returned after this request was declined.'
                      : 'at the time of this request.'}
              </p>
            )}
          </div>
          {(rewardsError || redemptionsError || balanceError) && (
            <div className="space-y-2">
              <p className="font-body text-body text-ink-secondary">
                Your request is saved. Some details couldn't refresh. Refresh the details instead of requesting again.
              </p>
              <Button variant="secondary" size="sm" onClick={refresh}>Refresh reward details</Button>
            </div>
          )}
          <Button variant="secondary" size="sm" onClick={() => setShowRequestHistory(true)}>View request history</Button>
        </ParchmentCard>
      )}

      {(!isParent || targetUserId) && (loadingBalance ? <Loader /> : balanceError ? (
        <ErrorAlert
          message={`Couldn't load your coin balance. ${balanceError}`}
          onRetry={reloadBalance}
        />
      ) : (
        <CoinBalanceCard
          coinBalance={coinBalance}
          isParent={isParent}
          canExchange={!isParentAccount}
          ownerName={isParent ? childName : undefined}
          onOpenExchange={() => setShowExchange(true)}
        />
      ))}

      {/* Ungated by role: these feed the parent's pending queues AND both
          roles' history accordions, so a swallowed failure silently drops a
          whole section for a child too. */}
      {redemptionsError && (
        <ErrorAlert
          message={`Couldn't load reward requests. ${redemptionsError}`}
          onRetry={reloadRedemptions}
        />
      )}
      {exchangesError && (
        <ErrorAlert
          message={`Couldn't load exchanges. ${exchangesError}`}
          onRetry={reloadExchanges}
        />
      )}
      {isParent && pendingRedemptionsError && (
        <ErrorAlert
          message={`Couldn't load pending reward requests. ${pendingRedemptionsError}`}
          onRetry={reloadPendingRedemptions}
        />
      )}
      {isParent && pendingExchangesError && (
        <ErrorAlert
          message={`Couldn't load pending exchanges. ${pendingExchangesError}`}
          onRetry={reloadPendingExchanges}
        />
      )}

      {isParent && (
        loadingPendingRedemptions ? <Loader /> : !pendingRedemptionsError && pending.length > 0 && (
          <section>
            <SectionHeader index={0} title="Pending reward requests" count={pending.length} />
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

      {isParent && <section id="reward-deliveries" aria-label="Awaiting reward delivery" className="space-y-3 scroll-mt-28">
        <SectionHeader title="Awaiting delivery" count={awaiting.length} />
        {deliveryNotice && <p role="status" className="text-body text-moss">{deliveryNotice}</p>}
        {loadingAwaiting ? <Loader /> : awaitingError
          ? <ErrorAlert message={`Couldn't load rewards awaiting delivery. ${awaitingError}`} onRetry={reloadAwaiting} />
          : awaiting.length > 0 ? <RewardDeliveryQueue rewards={awaiting} onDeliver={handleDeliver} />
            : <p className="text-body text-ink-secondary">No approved rewards waiting to be handed over.</p>}
      </section>}

      {isParent && (
        loadingPendingExchanges ? <Loader /> : !pendingExchangesError && pendingExchanges.length > 0 && (
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
          kicker="Browse available rewards"
        />
        <div className="mt-3 space-y-4">
          {loadingRewards ? <Loader /> : rewardsError ? (
            <ErrorAlert
              message={`Couldn't load the reward shop. ${rewardsError}`}
              onRetry={reloadRewards}
            />
          ) : (
            <>
              {rewards.length > 0 && (
                <div className="space-y-1">
                  <CatalogSearch
                    value={shopFilter}
                    onChange={setShopFilter}
                    placeholder="Search rewards…"
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
        <AccordionSection index={isParent ? 3 : 1} title="Reward request history" count={redemptions.length}>
          {redemptionsData?.count > redemptions.length && (
            <p className="font-script text-caption text-ink-whisper">
              Showing the {redemptions.length} most recent of {redemptionsData.count} reward requests.
            </p>
          )}
          <RedemptionHistory redemptions={redemptions} isParent={isParent} />
        </AccordionSection>
      )}

      {!personalParent && !loadingExchanges && exchanges.length > 0 && (
        <AccordionSection index={isParent ? 4 : 2} title="Exchange history" count={exchanges.length}>
          {exchangeData?.count > exchanges.length && (
            <p className="font-script text-caption text-ink-whisper">
              Showing the {exchanges.length} most recent of {exchangeData.count} exchanges.
            </p>
          )}
          <ExchangeHistory exchanges={exchanges} isParent={isParent} />
        </AccordionSection>
      )}

      {isParent && showRewardForm && (
        <RewardFormModal
          reward={editingReward}
          onClose={() => setShowRewardForm(false)}
          onSaved={() => { setShowRewardForm(false); refresh(); }}
        />
      )}

      {showRequestHistory && (
        <BottomSheet title="Reward request history" onClose={() => setShowRequestHistory(false)}>
          <div className="space-y-3">
            {loadingRedemptions && <Loader />}
            {redemptionsError && (
              <ErrorAlert
                message={`Your latest saved request is shown below. Couldn't refresh the full history. ${redemptionsError}`}
                onRetry={reloadRedemptions}
              />
            )}
            <RedemptionHistory redemptions={receiptHistory} isParent={isParent} />
            {redemptionsData?.count > receiptHistory.length && (
              <p className="font-body text-caption text-ink-secondary">
                Showing the {receiptHistory.length} most recent of {redemptionsData.count} reward requests.
              </p>
            )}
          </div>
        </BottomSheet>
      )}

      {isParent && showCoinAdjust && (
        <CoinAdjustModal
          initialChildId={targetUserId}
          childOptions={context.children}
          onClose={closeCoinAdjust}
          onSaved={() => { closeCoinAdjust(); refresh(); }}
        />
      )}

      {!isParentAccount && showExchange && (
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
          Coins are held when you request this reward. Digital items arrive
          after any required approval. Real-world rewards arrive when your
          parent hands them over. You can&apos;t cancel a request yourself;
          rejected requests return your coins.
        </p>
        <Button onClick={onConfirm} variant="primary" className="w-full">
          Request reward
        </Button>
        <Button onClick={onClose} variant="ghost" size="sm" className="w-full">
          Cancel
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
          This reward is out of stock. Get a notification when it's available again.
        </p>
        <Button onClick={onWishlist} variant="primary" size="sm" className="w-full">
          Notify me when restocked
        </Button>
        {similar.length > 0 && (
          <div>
            <div className="font-script text-body text-sheikah-teal-deep mt-2 mb-1.5">
              Similar rewards
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
                    {s.cost_coins} coins
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

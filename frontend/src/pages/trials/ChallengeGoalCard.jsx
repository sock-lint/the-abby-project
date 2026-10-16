import { useNavigate } from 'react-router-dom';
import { Pin } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ProgressBar from '../../components/ProgressBar';
import Button from '../../components/Button';
import BottomSheet from '../../components/BottomSheet';
import AddToCalendar from '../../components/AddToCalendar';
import CatalogIcon from '../../components/rpg/CatalogIcon';
import { goalActionPath, goalDate, goalDeadline, goalNumber, goalProgress, goalUnit } from './goalDisplay';

function GoalBody({ goal, timezone, showWhatCounts = true, showDeadline = true }) {
  const completed = goal.status === 'completed';
  const awarded = completed && goal.reward_receipt?.status === 'awarded';
  const rewards = awarded ? { coins: goal.reward_receipt.coins_awarded, xp: goal.reward_receipt.xp_awarded } : goal.rewards;
  const rewardItems = awarded ? goal.reward_receipt.items || [] : completed && goal.legacy ? [] : goal.rewards?.items || [];
  // Converted eggs are already included in the recorded Coin total.
  const deliveredItems = rewardItems.filter((item) => item.salvaged_to_coins === undefined);
  const ended = !['active', 'completed', 'upcoming'].includes(goal.status);
  return (
    <div className="space-y-3">
      <p className="font-body text-body text-ink-primary font-semibold">{goalProgress(goal)}</p>
      <ProgressBar value={Number(goal.progress)} max={Number(goal.target)} aria-label={`${goal.name} progress`} />
      <div className="flex flex-wrap gap-x-3 gap-y-1 font-body text-caption text-ink-secondary">
        {(showDeadline || completed || ended || goal.status === 'upcoming') && <span>{completed ? 'Completed' : ended ? 'Ended' : goal.status === 'upcoming' ? `Starts ${goalDate(goal.starts_at, goal.timezone || timezone)}` : `Ends ${goalDeadline(goal.ends_at, goal.timezone || timezone)}`}</span>}
        {goal.repeat_weekly && <span>Repeats weekly</span>}
      </div>
      {showWhatCounts && <p className="font-body text-body text-ink-secondary">{goal.what_counts}</p>}
      <p className="font-body text-caption text-ink-secondary">
        {awarded ? 'Bonus earned automatically' : completed ? goal.legacy ? 'Original completion bonus' : 'Bonus pending' : 'Completion bonus'}
        {rewards?.coins > 0 && ` · ${rewards.coins} coins`}
        {rewards?.xp > 0 && ` · ${rewards.xp} XP`}
        {deliveredItems.map((item) => ` · ${item.item_name || item.name} ×${item.quantity}`).join('')}
      </p>
    </div>
  );
}

export default function ChallengeGoalCard({ goal, timezone, onSelect, onPin, busy = false, showDeadline = true, isParent = false }) {
  return (
    <ParchmentCard as="article" aria-label={goal.name} className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex items-start gap-3">
          {goal.catalog_icon && <CatalogIcon assetId={goal.catalog_icon} size={40} alt={goal.name} className="shrink-0" />}
          <div className="min-w-0 space-y-1">
            <p className="font-body text-caption text-ink-secondary">{goal.origin === 'parent' ? isParent ? 'Parent goal' : 'From your parent' : goal.origin === 'legacy' || goal.legacy ? 'Saved challenge' : 'Bonus challenge'}</p>
            <h4 className="font-body font-bold text-lede text-ink-primary break-words">{goal.name}</h4>
          </div>
        </div>
        {goal.pinned && <span className="inline-flex shrink-0 items-center gap-1 text-caption text-sheikah-teal-deep"><Pin size={14} aria-hidden="true" /> Pinned</span>}
      </div>
      <GoalBody goal={goal} timezone={timezone} showDeadline={showDeadline} />
      <div className="flex flex-wrap gap-2">
        <Button data-challenge-view={goal.id} variant="secondary" size="sm" onClick={() => onSelect(goal)}>View {goal.name}</Button>
        {onPin && goal.status === 'active' && <Button variant="ghost" size="sm" aria-pressed={Boolean(goal.pinned)} disabled={busy} onClick={() => onPin(goal)}>
          {goal.pinned ? 'Unpin' : 'Pin to Today'}
        </Button>}
      </div>
    </ParchmentCard>
  );
}

export function ChallengeGoalDetail({ goal, timezone, onClose, onPin, busy, canAct = true }) {
  const navigate = useNavigate();
  const path = goalActionPath(goal.action);
  const close = () => {
    onClose();
    // Pinning can move/remount the opener while the sheet is open. Keep the
    // shared modal's normal restoration, with a live destination if it vanished.
    requestAnimationFrame(() => {
      if (document.activeElement !== document.body && document.activeElement?.isConnected) return;
      const view = [...document.querySelectorAll('[data-challenge-view]')].find((button) => button.dataset.challengeView === goal.id);
      const disclosure = ['active', 'upcoming'].includes(goal.status) ? 'bonus' : 'history';
      const target = view || document.querySelector(`[data-challenge-disclosure="${disclosure}"]`);
      target?.focus();
    });
  };
  return (
    <BottomSheet title={goal.name} onClose={close}>
      <div className="space-y-4">
        {goal.catalog_icon && <CatalogIcon assetId={goal.catalog_icon} size={64} alt={goal.name} />}
        {goal.description && <p className="font-body text-body text-ink-secondary">{goal.description}</p>}
        <GoalBody goal={goal} timezone={timezone} showWhatCounts={false} />
        {goal.participants?.length > 1 && <section className="space-y-2">
          <h3 className="font-body font-bold text-body text-ink-primary">Shared progress</h3>
          <ul className="space-y-1 font-body text-body text-ink-secondary">{goal.participants.map((participant) => <li key={participant.user}>{participant.user_name} · {goalNumber(participant.contribution)} {goalUnit(goal.unit, participant.contribution)}</li>)}</ul>
        </section>}
        {goal.rage_shield > 0 && <p className="font-body text-body text-ink-secondary">Boss shield adds {goal.rage_shield} damage to the target. It eases after active days.</p>}
        {goal.ends_at && <AddToCalendar event={{ id: goal.id, title: `Challenge deadline: ${goal.name}`, start: goal.ends_at, description: 'Challenge deadline.', path: '/quests?tab=trials' }} />}
        <div>
          <h3 className="font-body font-bold text-body text-ink-primary">What counts</h3>
          <p className="font-body text-body text-ink-secondary mt-1">{goal.what_counts}</p>
          <p className="font-body text-caption text-ink-secondary mt-2">Pinning only keeps this goal on Today. Every matching challenge progresses automatically.</p>
        </div>
        {goal.status === 'active' && <div className="flex flex-wrap gap-2">
          {path && canAct && <Button onClick={() => { onClose(); navigate(path); }}>{goal.action.label}</Button>}
          {onPin && <Button variant="secondary" aria-pressed={Boolean(goal.pinned)} disabled={busy} onClick={() => onPin(goal)}>{goal.pinned ? 'Unpin' : 'Pin to Today'}</Button>}
        </div>}
      </div>
    </BottomSheet>
  );
}

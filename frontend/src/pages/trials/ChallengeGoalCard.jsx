import { useNavigate } from 'react-router-dom';
import { Pin } from 'lucide-react';
import ProgressBar from '../../components/ProgressBar';
import Button from '../../components/Button';
import BottomSheet from '../../components/BottomSheet';
import AddToCalendar from '../../components/AddToCalendar';
import CatalogIcon from '../../components/rpg/CatalogIcon';
import RewardItem from '../../components/rpg/RewardItem';
import EarnedPetItemActions from '../../components/rpg/EarnedPetItemActions';
import AchievementCard from '../../components/cards/AchievementCard';
import { goalActionPath, goalNumber, goalProgress, goalUnit } from './goalDisplay';

function timingDate(value, timezone, withTime = false) {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return '';
  const options = { year: 'numeric', month: 'short', day: 'numeric',
    ...(withTime && { hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) };
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: timezone }).format(date);
  } catch {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone: 'UTC' }).format(date);
  }
}

function GoalBody({ goal, timezone, showWhatCounts = true, showExactDeadline = false, allowRewardActions = true, onRewardNavigate }) {
  const completed = goal.status === 'completed';
  const awarded = completed && goal.reward_receipt?.status === 'awarded';
  const rewards = awarded ? { coins: goal.reward_receipt.coins_awarded, xp: goal.reward_receipt.xp_awarded } : goal.rewards;
  const rewardItems = awarded ? goal.reward_receipt.items || [] : completed && goal.legacy ? [] : goal.rewards?.items || [];
  // Converted eggs are already included in the recorded Coin total.
  const deliveredItems = rewardItems.filter((item) => item.salvaged_to_coins === undefined);
  const ended = !['active', 'completed', 'upcoming'].includes(goal.status);
  const goalTimezone = goal.timezone || timezone || 'UTC';
  const starts = timingDate(goal.starts_at, goalTimezone);
  // Goal windows are half-open: Monday midnight belongs to the next week.
  // The short period lists included dates; details retain the exact boundary.
  const finalIncludedAt = goal.ends_at && Number.isFinite(Date.parse(goal.ends_at))
    ? new Date(Date.parse(goal.ends_at) - 1).toISOString() : null;
  const ends = timingDate(finalIncludedAt, goalTimezone);
  const deadline = timingDate(goal.ends_at, goalTimezone, true);
  const completedDate = timingDate(goal.completed_at, goalTimezone, true);
  return (
    <div className="space-y-3">
      <p className="font-body text-body text-ink-primary font-semibold">{goalProgress(goal)}</p>
      <ProgressBar value={Number(goal.progress)} max={Number(goal.target)} aria-label={`${goal.name} progress`} />
      <div className="flex flex-wrap gap-x-3 gap-y-1 font-body text-caption text-ink-secondary">
        <span>{completed ? 'Completed' : ended ? 'Period ended' : goal.status === 'upcoming' ? 'Upcoming' : 'Active'}</span>
        {goal.repeat_weekly && <span>Repeats weekly</span>}
      </div>
      <div className="space-y-1 font-body text-caption text-ink-secondary">
        {goal.ends_at === null && <p>No deadline</p>}
        {starts && ends && <p>Goal period <time dateTime={goal.starts_at}>{starts}</time> – <time dateTime={finalIncludedAt}>{ends}</time></p>}
        {showExactDeadline && deadline && <p>Counts work before <time dateTime={goal.ends_at}>{deadline}</time></p>}
        {completed && (completedDate
          ? <p>Completion recorded <time dateTime={goal.completed_at}>{completedDate}</time></p>
          : <p>Completion date unavailable</p>)}
      </div>
      {showWhatCounts && <p className="font-body text-body text-ink-secondary">{goal.what_counts}</p>}
      <p className="font-body text-caption text-ink-secondary">
        {awarded ? 'Bonus earned automatically' : completed ? goal.legacy ? 'Original completion bonus' : 'Bonus pending' : 'Completion bonus'}
        {rewards?.coins > 0 && ` · ${rewards.coins} coins`}
        {rewards?.xp > 0 && ` · ${rewards.xp} XP`}
      </p>
      {deliveredItems.length > 0 && <ul aria-label="Completion reward items" className="space-y-2">
        {deliveredItems.map((item, index) => <li key={item.item_id || item.item || index}><RewardItem item={item} /></li>)}
      </ul>}
      {awarded && allowRewardActions && <EarnedPetItemActions items={deliveredItems} onNavigate={onRewardNavigate} />}
    </div>
  );
}

export default function ChallengeGoalCard({ goal, timezone, onSelect, onPin, busy = false, isParent = false }) {
  return (
    <AchievementCard as="article" variant="tall" aria-label={goal.name}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1 basis-40 flex flex-wrap items-start gap-3">
              {goal.catalog_icon && <CatalogIcon assetId={goal.catalog_icon} size={40} alt={goal.name} className="shrink-0" />}
              <div className="min-w-0 flex-1 basis-32 space-y-1">
                <p className="font-body text-caption text-ink-secondary">{goal.origin === 'parent' ? isParent ? 'Parent goal' : 'From your parent' : goal.origin === 'legacy' || goal.legacy ? 'Saved challenge' : 'Bonus challenge'}</p>
                <h4 className="font-body font-bold text-lede text-ink-primary break-words [overflow-wrap:anywhere]">{goal.name}</h4>
              </div>
            </div>
            {goal.pinned && <span className="inline-flex shrink-0 items-center gap-1 text-caption text-sheikah-teal-deep"><Pin size={14} aria-hidden="true" /> Pinned</span>}
          </div>
          <GoalBody goal={goal} timezone={timezone} allowRewardActions={!isParent} />
          <div className="flex flex-wrap gap-2">
            <Button data-challenge-view={goal.id} className="min-w-0 max-w-full break-words [overflow-wrap:anywhere]" variant="secondary" size="sm" onClick={() => onSelect(goal)}>View {goal.name}</Button>
            {onPin && goal.status === 'active' && <Button variant="ghost" size="sm" aria-pressed={Boolean(goal.pinned)} disabled={busy} onClick={() => onPin(goal)}>
              {goal.pinned ? 'Unpin' : 'Pin to Today'}
            </Button>}
          </div>
        </div>
    </AchievementCard>
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
        <GoalBody goal={goal} timezone={timezone} showWhatCounts={false} showExactDeadline allowRewardActions={canAct} onRewardNavigate={onClose} />
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

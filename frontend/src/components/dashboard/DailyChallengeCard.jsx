import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getChallenges } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import AchievementCard from '../cards/AchievementCard';
import ProgressBar from '../ProgressBar';
import Button from '../Button';
import { goalDeadline } from '../../pages/trials/goalDisplay';
import PedestalImage from '../../pedestal/PedestalImage';
import '../../pedestal/storybook-accents.css';

export default function DailyChallengeCard({ refreshKey, challenge }) {
  const { isChild, user } = useRole();
  const navigate = useNavigate();
  const account = `${user?.id}:${getToken()}`;
  const fetch = useCallback(() => isChild && challenge === undefined
    ? getChallenges().then((result) => result.daily_bonus ? { ...result.daily_bonus, _bonusAccount: account } : null)
    : Promise.resolve(null), [isChild, challenge, account]);
  const { data, error, reload } = useApi(fetch, [account, isChild, refreshKey, challenge]);
  const bonus = challenge === undefined ? data?._bonusAccount === account ? data : null : challenge;
  if (!isChild) return null;
  if (error) return <AchievementCard variant="tall"><p role="alert" className="font-body text-body text-ink-secondary">{error}</p><Button variant="secondary" onClick={reload}>Retry today&apos;s bonus</Button></AchievementCard>;
  if (!bonus?.date) return null;
  return (
    <AchievementCard variant="tall" contentClassName="space-y-2">
      <div className="flex items-center gap-3">
        <span className="shrink-0" data-bonus-star={bonus.awarded ? 'awarded' : 'pending'} aria-hidden="true">
          <PedestalImage assetId={bonus.awarded ? 'star-lit' : 'star-unlit'} fallback={bonus.awarded ? '★' : '☆'} className="storybook-star storybook-bonus-star text-gold-leaf" />
        </span>
        <h2 className="min-w-0 break-words font-body font-bold text-lede text-ink-primary">Today&apos;s bonus</h2>
      </div>
      <p className="font-body text-body text-ink-primary">{bonus.goal}</p>
      <p className="font-body text-caption text-ink-secondary">Complete an approved task, or accumulate 10 minutes of project work or movement. Short sessions add together.</p>
      <ProgressBar value={bonus.completed ? 10 : Number(bonus.progress_minutes || 0)} max={10} aria-label="Today's bonus progress" />
      <p className="font-body text-caption text-ink-secondary" role="status">
        {bonus.awarded
          ? bonus.receipt_id ? `Bonus earned · +${bonus.coins_awarded} coins · +${bonus.xp_awarded} XP` : 'Bonus already earned'
          : bonus.completed ? 'Goal complete · Your bonus is being processed.'
            : `${Number(bonus.progress_minutes || 0)} / 10 minutes · Or complete one approved task`}
      </p>
      {!bonus.awarded && <p className="font-body text-caption text-ink-secondary">Automatically earns {bonus.coin_reward} coins and {bonus.xp_reward} XP.</p>}
      {bonus.ends_at && <p className="font-body text-caption text-ink-secondary">Ends {goalDeadline(bonus.ends_at, bonus.timezone)} · {bonus.timezone}</p>}
      {!bonus.completed && <Button variant="ghost" size="sm" onClick={() => navigate('/quests')}>View tasks</Button>}
    </AchievementCard>
  );
}

import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Hourglass } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { claimDailyChallenge, getDailyChallenge } from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { inkBleed } from '../../motion/variants';
import Button from '../Button';
import ParchmentCard from '../journal/ParchmentCard';
import ProgressBar from '../ProgressBar';
import RuneBadge from '../journal/RuneBadge';
import DailyChallengeClaimModal from './DailyChallengeClaimModal';

const CHALLENGE_LINKS = {
  clock_hour: { path: '/quests?tab=ventures', label: 'View projects' },
  chores: { path: '/quests?tab=duties', label: 'View chores' },
  habits: { path: '/quests?tab=rituals', label: 'View habits' },
  homework: { path: '/quests?tab=study', label: 'View homework' },
  milestone: { path: '/quests?tab=ventures', label: 'View projects' },
};

function challengeGoal(type, target, display) {
  switch (type) {
    case 'clock_hour': return `Clock ${target} ${target === 1 ? 'hour' : 'hours'} on a project today`;
    case 'chores': return `Complete ${target} ${target === 1 ? 'chore' : 'chores'} today`;
    case 'habits': return `Log ${target} positive habit ${target === 1 ? 'tap' : 'taps'} today`;
    case 'homework': return `Complete ${target} homework ${target === 1 ? 'assignment' : 'assignments'} today`;
    case 'milestone': return `Complete ${target} project ${target === 1 ? 'milestone' : 'milestones'} today`;
    default: return display?.replace(/\bN\b/g, String(target)) || "Complete today's task";
  }
}

function timeUntilMidnight(now = new Date()) {
  const next = new Date(now);
  next.setHours(24, 0, 0, 0);
  const ms = next.getTime() - now.getTime();
  if (ms <= 0) return 'soon';
  const totalMin = Math.floor(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  if (h <= 0) return `${m}m`;
  return `${h}h ${m}m`;
}

/**
 * DailyChallengeCard — daily bonus challenge for the child dashboard.
 *
 * Self-fetches today's DailyChallenge and renders one of:
 *   - in-progress / already-claimed (prior session): compact goal, progress,
 *     reward preview and task navigation, so the counter has clear meaning.
 *   - ready-to-claim: FULL celebration card — gold ring + Claim button
 *   - claimed (this session): FULL card with the inked success readout
 *
 * Hidden entirely for parents — the backend auto-creates a challenge for
 * whoever calls GET /api/challenges/daily/, so the role gate MUST short-
 * circuit the fetch rather than filter the render.
 */
export default function DailyChallengeCard({ refreshKey }) {
  const { isChild } = useRole();
  const navigate = useNavigate();

  const fetchChallenge = useCallback(
    () => (isChild ? getDailyChallenge() : Promise.resolve(null)),
    [isChild],
  );
  const { data, reload } = useApi(fetchChallenge, [isChild, refreshKey]);

  const [pending, setPending] = useState(false);
  const [claimed, setClaimed] = useState(null);
  const [claimError, setClaimError] = useState('');
  const [showClaimModal, setShowClaimModal] = useState(null);
  const [resetIn, setResetIn] = useState(() => timeUntilMidnight());

  // Recompute the midnight countdown every minute so the chip stays
  // honest without a per-render Date.now() in render. Cheap because the
  // card mounts on Today only.
  useEffect(() => {
    const id = setInterval(() => setResetIn(timeUntilMidnight()), 60_000);
    return () => clearInterval(id);
  }, []);

  if (!isChild || !data?.id) return null;

  const {
    challenge_type,
    challenge_type_display,
    current_progress = 0,
    target_value = 1,
    coin_reward = 0,
    xp_reward = 0,
    is_complete = false,
  } = data;

  const goal = challengeGoal(challenge_type, target_value, challenge_type_display);
  const taskLink = CHALLENGE_LINKS[challenge_type];
  const progressHelp = challenge_type === 'chores' || challenge_type === 'homework'
    ? 'Progress counts after parent approval.'
    : challenge_type === 'clock_hour'
      ? 'Counts when you clock out after at least an hour in one session.'
      : null;

  const activeClaim = claimed?.challengeId === data.id ? claimed : null;
  const sessionClaimed = activeClaim && !activeClaim.already_claimed;
  const priorClaim =
    (is_complete && coin_reward === 0 && xp_reward === 0) ||
    (activeClaim && activeClaim.already_claimed);
  const readyToClaim = is_complete && !sessionClaimed && !priorClaim;
  // Compact = nothing to celebrate right now (in progress, or claimed in a
  // prior session). The full card is reserved for the two reveal moments.
  const compact = !readyToClaim && !sessionClaimed;

  const onClaim = async () => {
    setPending(true);
    setClaimError('');
    try {
      const res = await claimDailyChallenge();
      setClaimed({ ...res, challengeId: data.id });
      // Trigger the reveal modal only when the server actually awarded
      // something this session — replays-after-midnight come back with
      // already_claimed=true and no celebration is owed.
      if (res && !res.already_claimed) {
        setShowClaimModal({ ...res, challengeId: data.id });
      }
      reload();
    } catch (err) {
      setClaimError(err?.message || 'Could not claim reward.');
    } finally {
      setPending(false);
    }
  };

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate">
      {showClaimModal?.challengeId === data.id && (
        <DailyChallengeClaimModal
          claim={showClaimModal}
          challengeLabel={goal}
          onDismiss={() => setShowClaimModal(null)}
        />
      )}
      {compact ? (
        <ParchmentCard tone="bright" className="!p-3">
          <div className="flex flex-wrap items-center gap-2 min-w-0">
            <Hourglass
              size={14}
              aria-hidden="true"
              className="shrink-0 text-sheikah-teal-deep"
            />
            <h2 className="min-w-0 font-display text-body text-ink-primary leading-tight">
              Daily challenge
            </h2>
            <span className="font-body text-caption text-ink-secondary tabular-nums ml-auto">
              Resets in {resetIn}
            </span>
          </div>
          <p className="mt-2 font-body text-body font-semibold text-ink-primary">{goal}</p>
          {!priorClaim && progressHelp && (
            <p className="mt-1 font-body text-caption text-ink-secondary">{progressHelp}</p>
          )}
          <p className="mt-1 font-body text-caption text-ink-secondary">
            {priorClaim
              ? 'Reward claimed · A new challenge arrives tomorrow.'
              : `Complete the goal, then claim +${coin_reward} coins and +${xp_reward} XP.`}
          </p>
          <div className="mt-2">
            <ProgressBar
              value={current_progress}
              max={target_value}
              aria-label={`${goal} progress`}
            />
            <div className="mt-1 font-body text-caption text-ink-secondary tabular-nums">
              {current_progress} / {target_value} complete
            </div>
          </div>
          {!priorClaim && taskLink && (
            <Button
              variant="ghost"
              size="sm"
              className="mt-1 -ml-3"
              onClick={() => navigate(taskLink.path)}
            >
              {taskLink.label} →
            </Button>
          )}
        </ParchmentCard>
      ) : (
        <ParchmentCard
          tone="bright"
          flourish
          className={
            readyToClaim
              ? 'ring-2 ring-gold-leaf/70 ring-offset-2 ring-offset-ink-page'
              : ''
          }
        >
          <div className="flex items-start justify-between gap-2">
            <div className="font-script text-sheikah-teal-deep text-caption uppercase tracking-wider">
              {sessionClaimed ? 'Reward earned' : 'Ready to claim'}
            </div>
            <RuneBadge tone="ink" size="sm">
              <span className="inline-flex items-center gap-1">
                <Hourglass size={10} aria-hidden="true" />
                <span>Resets in {resetIn}</span>
              </span>
            </RuneBadge>
          </div>
          <h2 className="font-display text-2xl text-ink-primary leading-tight mt-0.5">
            Daily challenge
          </h2>

          <div className="font-body text-body text-ink-secondary mt-1">
            {goal}
          </div>
          <div className="font-body text-caption text-ink-secondary mt-1">
            Complete the goal, then claim your bonus coins and XP.
          </div>

          <div className="mt-3">
            <ProgressBar
              value={current_progress}
              max={target_value}
              aria-label={`${goal} progress`}
            />
            <div className="mt-1 font-script text-caption text-ink-whisper tabular-nums">
              {current_progress} / {target_value}
            </div>
          </div>

          {sessionClaimed ? (
            <div
              role="status"
              aria-live="polite"
              className="mt-3 flex items-center gap-2"
            >
              <RuneBadge tone="gold">
                +{activeClaim.coins} coins · +{activeClaim.xp} XP earned.
              </RuneBadge>
            </div>
          ) : (
            <div className="mt-3 flex flex-col gap-2">
              <Button
                size="sm"
                onClick={onClaim}
                disabled={pending}
                aria-busy={pending || undefined}
                aria-label={`Claim ${coin_reward} coins and ${xp_reward} XP`}
                className="self-start"
              >
                {pending ? 'Claiming…' : `Claim reward · +${coin_reward} coins · +${xp_reward} XP`}
              </Button>
              {claimError && (
                // ``text-ember-deep`` is the theme's error ink — the raw
                // ``text-rose-700`` this replaced bypassed the per-cover
                // palette and went unreadable on the dark Vigil cover.
                <p role="alert" className="font-script text-body text-ember-deep">
                  {claimError}
                </p>
              )}
            </div>
          )}
        </ParchmentCard>
      )}
    </motion.div>
  );
}

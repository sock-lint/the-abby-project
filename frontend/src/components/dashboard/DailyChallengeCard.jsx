import { useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { claimDailyChallenge, getDailyChallenge } from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { inkBleed } from '../../motion/variants';
import Button from '../Button';
import ParchmentCard from '../journal/ParchmentCard';
import QuillProgress from '../QuillProgress';
import RuneBadge from '../journal/RuneBadge';

/**
 * DailyChallengeCard — "Today's Rite" card for the child dashboard.
 *
 * Self-fetches today's DailyChallenge and renders one of:
 *   - in-progress: progress bar + rewards preview
 *   - ready-to-claim: progress bar + primary Claim button
 *   - claimed (this session): success readout
 *   - already-claimed (prior session): static "Already claimed" line
 *
 * Hidden entirely for parents — the backend auto-creates a challenge for
 * whoever calls GET /api/challenges/daily/, so the role gate MUST short-
 * circuit the fetch rather than filter the render.
 */
export default function DailyChallengeCard() {
  const { isChild } = useRole();

  const fetchChallenge = useCallback(
    () => (isChild ? getDailyChallenge() : Promise.resolve(null)),
    [isChild],
  );
  const { data, reload } = useApi(fetchChallenge, [isChild]);

  const [pending, setPending] = useState(false);
  const [claimed, setClaimed] = useState(null);
  const [claimError, setClaimError] = useState('');

  if (!isChild || !data?.id) return null;

  const {
    challenge_type_display,
    current_progress = 0,
    target_value = 1,
    coin_reward = 0,
    xp_reward = 0,
    is_complete = false,
  } = data;

  const sessionClaimed = claimed && !claimed.already_claimed;
  const priorClaim =
    (is_complete && coin_reward === 0 && xp_reward === 0) ||
    (claimed && claimed.already_claimed);
  const readyToClaim = is_complete && !sessionClaimed && !priorClaim;

  const onClaim = async () => {
    setPending(true);
    setClaimError('');
    try {
      const res = await claimDailyChallenge();
      setClaimed(res);
      reload();
    } catch (err) {
      setClaimError(err?.message || 'Could not claim reward.');
    } finally {
      setPending(false);
    }
  };

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate">
      <ParchmentCard tone="bright" flourish>
        <div className="font-script text-sheikah-teal-deep text-xs uppercase tracking-wider">
          a small deed before the day turns
        </div>
        <h2 className="font-display italic text-2xl text-ink-primary leading-tight mt-0.5">
          Today&apos;s Rite
        </h2>

        {challenge_type_display && (
          <div className="font-body text-sm text-ink-secondary mt-1">
            {challenge_type_display}
          </div>
        )}
        <div className="font-script text-tiny text-ink-whisper mt-1">
          a fresh micro-quest each dawn — claim its coin once the bar fills
        </div>

        <div className="mt-3">
          <QuillProgress
            value={current_progress}
            max={target_value}
            aria-label={`${challenge_type_display || 'Daily rite'} progress`}
          />
          <div className="mt-1 font-script text-xs text-ink-whisper tabular-nums">
            {current_progress} / {target_value}
          </div>
        </div>

        {sessionClaimed && (
          <div
            role="status"
            aria-live="polite"
            className="mt-3 flex items-center gap-2"
          >
            <RuneBadge tone="gold">
              +{claimed.coins} coins · +{claimed.xp} XP — inked.
            </RuneBadge>
          </div>
        )}

        {!sessionClaimed && priorClaim && (
          <div className="mt-3 font-script text-sm text-ink-whisper">
            Already claimed — a new rite opens at midnight.
          </div>
        )}

        {!sessionClaimed && !priorClaim && readyToClaim && (
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
              <p role="alert" className="font-script text-sm text-rose-700">
                {claimError}
              </p>
            )}
          </div>
        )}

        {!sessionClaimed && !priorClaim && !readyToClaim && (
          <div className="mt-3 font-script text-xs text-ink-whisper">
            Reward waiting: {coin_reward} coins · {xp_reward} XP
          </div>
        )}
      </ParchmentCard>
    </motion.div>
  );
}

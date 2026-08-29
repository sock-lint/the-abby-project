import { useCallback, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Hourglass } from 'lucide-react';
import { claimDailyChallenge, getDailyChallenge } from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { inkBleed } from '../../motion/variants';
import Button from '../Button';
import ParchmentCard from '../journal/ParchmentCard';
import QuillProgress from '../QuillProgress';
import RuneBadge from '../journal/RuneBadge';
import DailyChallengeClaimModal from './DailyChallengeClaimModal';

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
 * DailyChallengeCard — "Today's Rite" card for the child dashboard.
 *
 * Self-fetches today's DailyChallenge and renders one of:
 *   - in-progress / already-claimed (prior session): COMPACT single row —
 *     icon + "Today's Rite · 1 / 2 · resets in 5h" + thin progress bar.
 *     These are the everyday states; the full flourish card here pushed
 *     the child's quest log a whole screen down on phones.
 *   - ready-to-claim: FULL celebration card — gold ring + Claim button
 *   - claimed (this session): FULL card with the inked success readout
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
  // Compact = nothing to celebrate right now (in progress, or claimed in a
  // prior session). The full card is reserved for the two reveal moments.
  const compact = !readyToClaim && !sessionClaimed;

  const onClaim = async () => {
    setPending(true);
    setClaimError('');
    try {
      const res = await claimDailyChallenge();
      setClaimed(res);
      // Trigger the reveal modal only when the server actually awarded
      // something this session — replays-after-midnight come back with
      // already_claimed=true and no celebration is owed.
      if (res && !res.already_claimed) {
        setShowClaimModal(res);
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
      {showClaimModal && (
        <DailyChallengeClaimModal
          claim={showClaimModal}
          challengeLabel={challenge_type_display}
          onDismiss={() => setShowClaimModal(null)}
        />
      )}
      {compact ? (
        <ParchmentCard tone="bright" className="!p-3">
          <div className="flex items-center gap-2 min-w-0">
            <Hourglass
              size={14}
              aria-hidden="true"
              className="shrink-0 text-sheikah-teal-deep"
            />
            <h2 className="min-w-0 font-display italic text-body text-ink-primary leading-tight">
              Today&apos;s Rite
              <span className="font-script text-caption text-ink-whisper tabular-nums">
                {' · '}
                {priorClaim
                  ? 'already claimed — a new rite opens at midnight'
                  : `${current_progress} / ${target_value} · resets in ${resetIn}`}
              </span>
            </h2>
          </div>
          <div className="mt-1.5">
            <QuillProgress
              value={current_progress}
              max={target_value}
              aria-label={`${challenge_type_display || 'Daily rite'} progress`}
            />
          </div>
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
              a small deed before the day turns
            </div>
            <RuneBadge tone="ink" size="sm">
              <span className="inline-flex items-center gap-1">
                <Hourglass size={10} aria-hidden="true" />
                <span>resets in {resetIn}</span>
              </span>
            </RuneBadge>
          </div>
          <h2 className="font-display italic text-2xl text-ink-primary leading-tight mt-0.5">
            Today&apos;s Rite
          </h2>

          {challenge_type_display && (
            <div className="font-body text-body text-ink-secondary mt-1">
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
                +{claimed.coins} coins · +{claimed.xp} XP — inked.
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

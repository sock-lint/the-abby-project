import { Crown, Flame, Star, Award } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import BoostStrip from '../../components/rpg/BoostStrip';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import TrophySlot from './TrophySlot';

/**
 * Compact identity, equipped title/frame and earned trophy. Stats summarize
 * confirmed activity without pushing customization below a large hero.
 */
export default function SigilFrontispiece({ profile, profilePicture, onOpenTrophyPicker, children }) {
  const displayName = profile.display_name || profile.username || '\u2014';
  const initial = (displayName[0] || '?').toUpperCase();
  const level = profile.level ?? 1;
  const atHighestLevel = profile.xp_needed_for_level === 0 && level > 0;
  const levelProgress = profile.xp_needed_for_level > 0
    ? Math.max(0, Math.min(100, ((profile.xp_in_level ?? 0) / profile.xp_needed_for_level) * 100))
    : atHighestLevel ? 100 : 0;
  const tier = tierForProgress({
    unlocked: true,
    progressPct: levelProgress,
    level,
  });

  const titleText =
    profile.active_title?.metadata?.text || profile.active_title?.name;
  const frameColor =
    profile.active_frame?.metadata?.border_color || null;

  return (
    <ParchmentCard
      variant="plain"
      tone="bright"
      className="overflow-hidden"
    >
      <div className="flex items-center gap-3">
        <div
          className="relative inline-flex shrink-0"
          style={
            frameColor
              ? {
                  boxShadow: `0 0 0 3px var(--color-ink-page-aged), 0 0 0 4px ${frameColor}, 0 0 0 6px var(--color-ink-page-shadow)`,
                  borderRadius: '1rem',
                }
              : undefined
          }
        >
          {profilePicture ? <img src={profilePicture} alt="Your profile picture" className="size-16 rounded-2xl object-cover" /> : <IlluminatedVersal
            letter={initial}
            size="md"
            tier={tier}
            progressPct={levelProgress}
          />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="font-body font-semibold text-sheikah-teal-deep text-caption leading-snug mb-1">
            Your profile
          </div>
          <h1 className="font-body font-bold text-2xl text-ink-primary leading-tight break-words">
            {displayName}
          </h1>
          {titleText && (
            <div className="mt-1 font-body font-semibold text-body text-gold-leaf flex items-start gap-1">
              <Crown size={14} className="mt-1 shrink-0 text-gold-leaf" />
              <span className="min-w-0 break-words [overflow-wrap:anywhere]">{titleText}</span>
            </div>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <RuneBadge tone="teal" size="sm">level {level}</RuneBadge>
            {profile.xp_needed_for_level > 0 && (
              <span className="font-body text-caption text-ink-secondary tabular-nums">
                {Math.round(levelProgress)}% toward the next level
              </span>
            )}
            {atHighestLevel && (
              <span className="font-body text-caption text-ink-secondary">Highest level</span>
            )}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <TrophySlot badge={profile.active_trophy_badge} frame={profile.active_frame} onOpen={onOpenTrophyPicker} compact />
      </div>

      {children}

      <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-ink-page-shadow pt-3 font-body">
        <div>
          <dt className="flex items-center gap-1 text-caption text-ink-secondary"><Flame size={13} aria-hidden="true" /> Streak</dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.login_streak ?? 0} days</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-caption text-ink-secondary"><Star size={13} aria-hidden="true" /> Perfect days</dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.perfect_days_count ?? 0}</dd>
        </div>
        <div>
          <dt className="flex items-center gap-1 text-caption text-ink-secondary"><Award size={13} aria-hidden="true" /> Best streak</dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.longest_login_streak ?? 0} days</dd>
        </div>
      </dl>

      <BoostStrip profile={profile} className="mt-3" />
    </ParchmentCard>
  );
}

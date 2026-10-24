import { Flame, Star, Award } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import BoostStrip from '../../components/rpg/BoostStrip';
import IdentitySummary from '../../components/identity/IdentitySummary';
import TrophySlot from './TrophySlot';

/**
 * Compact identity, equipped title/frame and earned trophy. Stats summarize
 * confirmed activity without pushing customization below a large hero.
 */
export default function SigilFrontispiece({ profile, profilePicture, onOpenTrophyPicker, children }) {
  const displayName = profile.display_name || profile.username || '\u2014';
  const level = profile.level;
  const atHighestLevel = profile.xp_needed_for_level === 0 && level > 0;
  const levelProgress = profile.xp_needed_for_level > 0
    ? Math.max(0, Math.min(100, ((profile.xp_in_level ?? 0) / profile.xp_needed_for_level) * 100))
    : atHighestLevel ? 100 : 0;
  return (
    <ParchmentCard
      variant="plain"
      tone="bright"
      className="overflow-hidden"
    >
      <div className="font-body font-semibold text-sheikah-teal-deep text-caption leading-snug mb-2">
        Your profile
      </div>
      <IdentitySummary as="div" nameAs="h1" name={displayName} avatar={profilePicture}
        frame={profile.active_frame} title={profile.active_title} badge={profile.active_trophy_badge}
        level={level} portraitSize="lg" imageAlt="Your profile picture" />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {profile.xp_needed_for_level > 0 && (
          <span className="font-body text-caption text-ink-secondary tabular-nums">
            {Math.round(levelProgress)}% toward the next level
          </span>
        )}
        {atHighestLevel && (
          <span className="font-body text-caption text-ink-secondary">Highest level</span>
        )}
      </div>

      {children}

      <div className="mt-4">
        <TrophySlot badge={profile.active_trophy_badge} onOpen={onOpenTrophyPicker} compact />
      </div>

      <dl className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(min(100%,6em),1fr))] gap-3 border-t border-ink-page-shadow pt-3 font-body text-caption">
        <div>
          <dt className="flex items-start gap-1 text-caption text-ink-secondary"><Flame size={13} aria-hidden="true" className="mt-0.5 shrink-0" /><span className="min-w-0 break-words [overflow-wrap:anywhere]">Streak</span></dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.login_streak ?? 0} days</dd>
        </div>
        <div>
          <dt className="flex items-start gap-1 text-caption text-ink-secondary"><Star size={13} aria-hidden="true" className="mt-0.5 shrink-0" /><span className="min-w-0 break-words [overflow-wrap:anywhere]">Perfect days</span></dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.perfect_days_count ?? 0}</dd>
        </div>
        <div>
          <dt className="flex items-start gap-1 text-caption text-ink-secondary"><Award size={13} aria-hidden="true" className="mt-0.5 shrink-0" /><span className="min-w-0 break-words [overflow-wrap:anywhere]">Best streak</span></dt>
          <dd className="mt-1 text-body font-bold text-ink-primary tabular-nums">{profile.longest_login_streak ?? 0} days</dd>
        </div>
      </dl>

      <BoostStrip profile={profile} className="mt-3" />
    </ParchmentCard>
  );
}

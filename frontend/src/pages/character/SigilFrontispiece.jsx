import { Crown } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import IlluminatedVersal from '../achievements/IlluminatedVersal';
import { tierForProgress } from '../achievements/mastery.constants';
import StreakGlyph from './StreakGlyph';
import TrophySlot from './TrophySlot';

/**
 * SigilFrontispiece — the hero frontispiece plate of `/sigil`. A bound,
 * sealed parchment that reads like the inside-cover plate of a leather
 * journal: oversized illuminated initial on the verso, name + title +
 * level strap in the middle, and the trophy seal on the recto.
 *
 * Below the hero row, three StreakGlyph pips visualise the RPG vitals
 * (current streak, perfect days, best streak). The active streak flame
 * animates; the other two are static awards.
 */
export default function SigilFrontispiece({ profile, onOpenTrophyPicker }) {
  const displayName = profile.display_name || profile.username || '\u2014';
  const initial = (displayName[0] || '?').toUpperCase();
  const level = profile.level ?? 1;
  const levelProgress = profile.xp_in_level && profile.xp_needed_for_level
    ? (profile.xp_in_level / profile.xp_needed_for_level) * 100
    : Math.max(0, Math.min(100, level * 10));
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
      variant="sealed"
      tone="bright"
      flourish
      seal="bottom-right"
      className="overflow-hidden"
    >
      <div className="grid grid-cols-1 md:grid-cols-[auto_1fr_auto] items-center gap-6 pr-4">
        <div
          className="relative"
          style={
            frameColor
              ? {
                  boxShadow: `0 0 0 3px var(--color-ink-page-aged), 0 0 0 4px ${frameColor}, 0 0 0 6px var(--color-ink-page-shadow)`,
                  borderRadius: '12px',
                }
              : undefined
          }
        >
          <IlluminatedVersal
            letter={initial}
            size="xl"
            tier={tier}
            progressPct={levelProgress}
          />
        </div>

        <div className="min-w-0 text-center md:text-left">
          <div className="font-script text-sheikah-teal-deep text-base leading-snug">
            · the frontispiece ·
          </div>
          <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight break-words">
            {displayName}
          </h1>
          {titleText && (
            <div className="mt-1 font-script text-lede text-gold-leaf flex items-center justify-center md:justify-start gap-1">
              <Crown size={14} className="text-gold-leaf" /> {titleText}
            </div>
          )}
          <div className="mt-2 flex items-center justify-center md:justify-start gap-2">
            <RuneBadge tone="teal" size="md">level {level}</RuneBadge>
            <span className="font-script text-caption text-ink-whisper tabular-nums">
              · {Math.round(levelProgress)}% to next
            </span>
          </div>
        </div>

        <div className="flex justify-center md:justify-end">
          <TrophySlot
            badge={profile.active_trophy_badge}
            onOpen={onOpenTrophyPicker}
          />
        </div>
      </div>

      <div className="mt-5 grid grid-cols-3 gap-3">
        <StreakGlyph
          kind="streak"
          value={profile.login_streak ?? 0}
          longestStreak={profile.longest_login_streak ?? 0}
        />
        <StreakGlyph kind="perfect" value={profile.perfect_days_count ?? 0} />
        <StreakGlyph kind="best" value={profile.longest_login_streak ?? 0} />
      </div>
    </ParchmentCard>
  );
}

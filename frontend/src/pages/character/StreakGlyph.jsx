import { Star, Award } from 'lucide-react';
import StreakFlame from '../../components/journal/StreakFlame';
import { PROGRESS_TIER } from '../../components/atlas/mastery.constants';
import { streakTier } from './character.constants';

const TIER_CHIP = {
  locked:   PROGRESS_TIER.locked,
  nascent:  PROGRESS_TIER.nascent,
  rising:   PROGRESS_TIER.rising,
  cresting: PROGRESS_TIER.cresting,
  gilded:   PROGRESS_TIER.gilded,
};

/**
 * StreakGlyph — one of three vital pips on the Frontispiece. Three kinds:
 *
 *   • `streak`  — current login streak; embeds StreakFlame for animation.
 *   • `perfect` — cumulative perfect-day count (Star icon, gold tone).
 *   • `best`    — longest-ever streak (Award laurel icon, royal tone).
 *
 * Each pip is a soft stat cell: an icon above, a clear numeral
 * in the middle, and a readable label beneath. Color tone comes from the
 * streak ladder for the streak pip; perfect-days/best both render in a
 * static "achievement" tone so only the streak animates.
 */
export default function StreakGlyph({
  kind,
  value = 0,
  longestStreak = 0,
}) {
  const numeric = Number(value) || 0;

  if (kind === 'streak') {
    const tier = streakTier(numeric).tier;
    const chip = TIER_CHIP[tier] ?? TIER_CHIP.locked;
    return (
      <div
        data-streak-glyph="streak"
        data-tier={tier}
        className="rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-2 sm:p-3 text-center"
      >
        <div className="flex items-center justify-center">
          <StreakFlame streak={numeric} longest={longestStreak} className="w-full flex-col sm:w-auto sm:flex-row scale-90 origin-center" />
        </div>
        <div className={`mt-1 font-body font-semibold text-caption ${chip.chip}`}>
          streak
        </div>
      </div>
    );
  }

  if (kind === 'perfect') {
    return (
      <div
        data-streak-glyph="perfect"
        className="rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-2 sm:p-3 text-center"
      >
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-2xl bg-ink-page">
          <Star size={20} aria-hidden="true" className="text-gold-leaf" />
        </div>
        <div className="mt-1 font-body font-bold text-lede text-ink-primary tabular-nums">
          {numeric}
        </div>
        <div className="font-body text-caption text-ink-whisper leading-tight">
          perfect days
        </div>
      </div>
    );
  }

  // best
  return (
    <div
      data-streak-glyph="best"
      className="rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-2 sm:p-3 text-center"
    >
      <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-2xl bg-ink-page">
        <Award size={20} aria-hidden="true" className="text-royal" />
      </div>
      <div className="mt-1 font-body font-bold text-lede text-ink-primary tabular-nums">
        {numeric}
      </div>
      <div className="font-body text-caption text-ink-whisper leading-tight">
        best streak
      </div>
    </div>
  );
}

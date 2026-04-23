import { Star, Award } from 'lucide-react';
import StreakFlame from '../../components/journal/StreakFlame';
import { PROGRESS_TIER } from '../achievements/mastery.constants';
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
 * Each pip is an illuminated stat cell: a glyph above, large rune numeral
 * in the middle, and a script label beneath. Color tone comes from the
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
        className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3 text-center shadow-[inset_0_1px_0_rgba(255,248,224,0.4)]"
      >
        <div className="flex items-center justify-center">
          <StreakFlame streak={numeric} longest={longestStreak} className="scale-90 origin-center" />
        </div>
        <div className={`mt-1 font-rune uppercase tracking-wider text-micro ${chip.chip}`}>
          streak
        </div>
      </div>
    );
  }

  if (kind === 'perfect') {
    return (
      <div
        data-streak-glyph="perfect"
        className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3 text-center shadow-[inset_0_1px_0_rgba(255,248,224,0.4)]"
      >
        <Star size={20} className="mx-auto text-gold-leaf" />
        <div className="mt-1 font-rune font-bold text-lede text-ink-primary tabular-nums">
          {numeric}
        </div>
        <div className="font-script text-caption text-ink-whisper leading-tight">
          perfect days
        </div>
      </div>
    );
  }

  // best
  return (
    <div
      data-streak-glyph="best"
      className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/60 p-3 text-center shadow-[inset_0_1px_0_rgba(255,248,224,0.4)]"
    >
      <Award size={20} className="mx-auto text-royal" />
      <div className="mt-1 font-rune font-bold text-lede text-ink-primary tabular-nums">
        {numeric}
      </div>
      <div className="font-script text-caption text-ink-whisper leading-tight">
        best streak
      </div>
    </div>
  );
}

import { PROGRESS_TIER, RARITY_HALO } from './mastery.constants';

/**
 * IlluminatedVersal — the drop-capital letter that anchors a SkillVerse. The
 * letter is drawn twice: an unilluminated stroke in ink-whisper sits
 * underneath, and an overlay in gold-leaf is clipped to the letterform and
 * filled from the bottom up by `progressPct`. Mastered or cresting versals
 * wear a RARITY_HALO glow-ring; locked versals stay flat parchment.
 *
 * Decorative — the adjacent verse body carries the semantic text, so this
 * component marks itself aria-hidden.
 */
const SIZES = {
  sm: { box: 'w-10 h-10', text: 'text-2xl' },
  md: { box: 'w-12 h-12', text: 'text-3xl' },
  lg: { box: 'w-16 h-16', text: 'text-4xl' },
  xl: { box: 'w-24 h-24', text: 'text-6xl' },
};

// Map progress tier onto the rarity halo palette so mastery visually
// inherits from the same vocabulary that makes Badges feel earned.
const TIER_TO_HALO = {
  gilded: RARITY_HALO.legendary,
  cresting: RARITY_HALO.epic,
  rising: RARITY_HALO.rare,
  nascent: RARITY_HALO.uncommon,
  locked: '',
};

function tierKeyOf(tier) {
  for (const key of Object.keys(PROGRESS_TIER)) {
    if (PROGRESS_TIER[key] === tier) return key;
  }
  return 'locked';
}

export default function IlluminatedVersal({
  letter,
  progressPct = 0,
  tier,
  size = 'md',
  showHalo = true,
  className = '',
}) {
  const glyph = (letter || '✦').slice(0, 1).toUpperCase();
  const key = tierKeyOf(tier);
  const mastered = key === 'gilded' || key === 'cresting';
  const halo = showHalo && mastered ? TIER_TO_HALO[key] : '';
  const locked = key === 'locked';
  const sz = SIZES[size] || SIZES.md;
  const fillPct = Math.max(0, Math.min(100, progressPct));

  return (
    <span
      aria-hidden="true"
      data-versal="true"
      data-tier={key}
      data-progress={Math.round(fillPct)}
      style={{ '--versal-fill': `${fillPct}%` }}
      className={`relative inline-flex items-center justify-center rounded-md border border-ink-page-shadow bg-ink-page-aged overflow-hidden shrink-0 ${sz.box} ${halo} ${className}`}
    >
      {/* Base (unilluminated) letter — the stone carving under the gilt. */}
      <span
        className={`absolute inset-0 flex items-center justify-center font-display italic font-bold leading-none ${sz.text} ${
          locked ? 'text-ink-whisper/60' : 'text-ink-whisper'
        }`}
      >
        {glyph}
      </span>
      {/* Gilt overlay — the same letter, clipped, filled gold-leaf from the
          bottom. Hidden when locked so there's nothing to illuminate yet.
          The gradient + background-clip live in the .versal-gilt CSS class
          so React doesn't warn about mixing shorthand + long-hand inline. */}
      {!locked && (
        <span
          data-versal-gilt="true"
          className={`versal-gilt absolute inset-0 flex items-center justify-center font-display italic font-bold leading-none ${sz.text}`}
        >
          {glyph}
        </span>
      )}
      {/* Inner highlight — subtle page-curl sheen. Matches ParchmentCard's
          inset shadow vocabulary. */}
      <span
        aria-hidden="true"
        className="absolute inset-0 pointer-events-none rounded-md shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset]"
      />
    </span>
  );
}

// Shared by Skills (TomeSpine, FolioSpread, ChapterRubric, SkillVerse,
// IlluminatedVersal) and Badges (BadgeSigil, BadgeDetailSheet, CollectionFolio,
// IncipitBand). Lives in a .js file because react-refresh/only-export-components
// forbids non-component exports from .jsx.

// Progress tier drives the gilt color on TomeSpine foot-bands, SkillVerse
// level straps, and IlluminatedVersal fill. Tailwind class strings resolve
// through cover tokens, not hex — so every journal cover (hyrule / vigil /
// sunlit / snowquill / verdant / harvest) gets its own contrast-tuned shade
// without branching here.
export const PROGRESS_TIER = {
  locked: { bar: 'bg-ink-page-shadow/60', chip: 'text-ink-whisper' },
  nascent: { bar: 'bg-moss', chip: 'text-moss' },
  rising: { bar: 'bg-sheikah-teal-deep', chip: 'text-sheikah-teal-deep' },
  cresting: { bar: 'bg-ember', chip: 'text-ember-deep' },
  gilded: { bar: 'bg-gold-leaf', chip: 'text-ember-deep' },
};

export function tierForProgress({ unlocked, progressPct, level, maxLevel = 6 }) {
  if (!unlocked) return PROGRESS_TIER.locked;
  if (level >= maxLevel) return PROGRESS_TIER.gilded;
  if (progressPct >= 90) return PROGRESS_TIER.gilded;
  if (progressPct >= 60) return PROGRESS_TIER.cresting;
  if (progressPct >= 25) return PROGRESS_TIER.rising;
  return PROGRESS_TIER.nascent;
}

// Radial glow behind a badge sigil. Shadow uses the cover token so a Vigil
// (dark) user gets the same gold-leaf halo the variable resolves to for them.
export const RARITY_HALO = {
  common: 'shadow-[0_0_18px_rgba(123,158,99,0.35)] ring-1 ring-moss/40',
  uncommon: 'shadow-[0_0_22px_rgba(64,140,140,0.40)] ring-1 ring-sheikah-teal/45',
  rare: 'shadow-[0_0_26px_rgba(76,94,158,0.45)] ring-1 ring-royal/50',
  epic: 'shadow-[0_0_30px_rgba(191,84,56,0.50)] ring-1 ring-ember/55',
  legendary: 'shadow-[0_0_36px_rgba(216,176,88,0.60)] ring-2 ring-gold-leaf/70',
};

export const CHAPTER_NUMERALS = [
  '§I',
  '§II',
  '§III',
  '§IV',
  '§V',
  '§VI',
  '§VII',
  '§VIII',
  '§IX',
  '§X',
  '§XI',
  '§XII',
];

export function chapterMark(i) {
  return CHAPTER_NUMERALS[i] ?? `§${i + 1}`;
}

export function countIlluminated(subjects) {
  let illuminated = 0;
  let total = 0;
  for (const subject of subjects ?? []) {
    const skills = subject?.skills;
    if (!Array.isArray(skills)) continue;
    for (const skill of skills) {
      total += 1;
      if (skill.unlocked && skill.xp_points > 0) illuminated += 1;
    }
  }
  return { illuminated, total };
}

export const RECENT_EARNED_DAYS = 7;

export function isRecentlyEarned(earnedAt) {
  if (!earnedAt) return false;
  const earned = Date.parse(earnedAt);
  if (Number.isNaN(earned)) return false;
  const cutoff = Date.now() - RECENT_EARNED_DAYS * 24 * 60 * 60 * 1000;
  return earned >= cutoff;
}

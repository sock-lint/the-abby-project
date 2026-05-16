// Shared helpers for the Quest folios — mapping the per-page tier
// concepts (Project difficulty, Homework effort_level) onto the Atlas
// rarity vocabulary so a RarityStrand can sit on the verso of each folio
// without inventing new tier ladders.
//
// Lives in a .js file because react-refresh/only-export-components forbids
// non-component exports from .jsx — same pattern as the cohort's
// mastery.constants.js + the Reliquary's collections.constants.js.

import { RARITY_KEYS } from '../../components/atlas/mastery.constants';

// 1-5 ladders fan out cleanly across the five rarity keys: 1→common,
// 2→uncommon, 3→rare, 4→epic, 5→legendary. Clamped at both ends so a
// missing or off-scale value lands on common rather than crashing the
// reduce in buildRarityCounts.
export function difficultyToRarity(level) {
  const n = Math.max(1, Math.min(5, Math.round(Number(level) || 1)));
  return RARITY_KEYS[n - 1];
}

// Homework effort_level uses the same 1-5 scale as Project.difficulty;
// reuse the mapping rather than maintaining two parallel ladders.
export const effortToRarity = difficultyToRarity;

// RarityStrand expects { common: {earned, total}, …, legendary: {…} }.
// `mapper(item)` returns one of RARITY_KEYS; `isEarned(item)` decides
// whether to count an item against the segment's fill (e.g. "completed"
// for ventures, "approved" for homework). Empty buckets stay at 0 so the
// strand still paints the trough.
export function buildRarityCounts(items, mapper, isEarned = () => false) {
  const seed = RARITY_KEYS.reduce((acc, key) => {
    acc[key] = { earned: 0, total: 0 };
    return acc;
  }, {});
  for (const item of items ?? []) {
    const key = mapper(item);
    if (!RARITY_KEYS.includes(key)) continue;
    seed[key].total += 1;
    if (isEarned(item)) seed[key].earned += 1;
  }
  return seed;
}

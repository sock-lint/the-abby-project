// Pure-data exports for the Bestiary Codex's chapter taxonomy. Mirrors the
// shape of pages/achievements/collections.constants.js so the Codex and the
// Reliquary speak the same vocabulary. Lives in a .js file (not .jsx) so the
// react-refresh/only-export-components lint rule stays satisfied.
//
// Chapters bucket every authored species by how far the user has progressed
// with it. Tier vocabulary matches PROGRESS_TIER from components/atlas — the
// shelf spines tint themselves based on that.

import { chapterMark, PROGRESS_TIER, RARITY_KEYS } from '../../../components/atlas/mastery.constants';
import { acquisitionRarity } from '../../../companion/rarity';

// Chapter definitions. `rubric` is the number the chapter marker renders;
// `letter` is the IlluminatedVersal drop-cap. `tier` is the spine-tint hint
// — `groupSpeciesByChapter` still computes a progress-based tier per chapter
// at call time so empty chapters fall back to `locked` correctly.
export const CHAPTERS = [
  {
    id: 'mythic',
    name: 'Complete',
    letter: 'C',
    rubric: chapterMark(0),
    kicker: 'Every available variant fully grown',
    tier: PROGRESS_TIER.gilded,
  },
  {
    id: 'bonded',
    name: 'Evolved',
    letter: 'E',
    rubric: chapterMark(1),
    kicker: 'At least one companion fully grown',
    tier: PROGRESS_TIER.cresting,
  },
  {
    id: 'hatched',
    name: 'Hatched',
    letter: 'H',
    rubric: chapterMark(2),
    kicker: 'A companion hatched and still growing',
    tier: PROGRESS_TIER.rising,
  },
  {
    id: 'silhouettes',
    name: 'Undiscovered',
    letter: 'U',
    rubric: chapterMark(3),
    kicker: 'Hatch a companion to discover its species',
    tier: PROGRESS_TIER.locked,
  },
];

// Classify a single species → chapter id. Order matters: a species in every
// potion variant lands in `mythic` even though `bonded` would also match.
export function chapterIdForSpecies(species) {
  if (!species) return 'silhouettes';
  if (!species.discovered) return 'silhouettes';
  const ownedVariants = species.owned_mount_potion_ids?.length || 0;
  const totalVariants = species.available_potions?.length || 0;
  const hasMount = ownedVariants > 0;
  const hasPet = (species.owned_pet_ids?.length || 0) > 0;
  if (hasMount && totalVariants > 0 && ownedVariants >= totalVariants) {
    return 'mythic';
  }
  if (hasMount) return 'bonded';
  if (hasPet) return 'hatched';
  // Discovered without a tracked pet/mount row shouldn't happen in practice
  // (PetCodexView only flags discovered=true when either list is non-empty),
  // but if it does, fall back to hatched so the species still appears.
  return 'hatched';
}

// Aggregate the per-chapter rarity strand. We count each species' available
// potion-variants by acquisition rarity (preserving higher saved potion tiers):
// `total` is the variant count, `earned` is how
// many of those variants the user owns as a mount. This way the strand reads
// "how full is your shelf of mounts in this chapter" — matching the Sigil
// Codex pattern where the strand is sealed-of-total per rarity.
function buildRarityCounts(speciesList) {
  const counts = {};
  RARITY_KEYS.forEach((key) => {
    counts[key] = { earned: 0, total: 0 };
  });
  for (const species of speciesList) {
    const owned = new Set(species.owned_mount_potion_ids || []);
    for (const potion of species.available_potions || []) {
      const rarity = acquisitionRarity(species, potion);
      if (!counts[rarity]) continue;
      counts[rarity].total += 1;
      if (owned.has(potion.id)) counts[rarity].earned += 1;
    }
  }
  return counts;
}

// Group every species into chapter buckets. Returns the full ordered chapter
// list (including empty chapters) so the shelf renders a complete skeleton
// — empty chapters still draw a spine, matching SigilCodex's behaviour.
export function groupSpeciesByChapter(species = []) {
  const buckets = new Map(CHAPTERS.map((c) => [c.id, []]));
  for (const sp of species) {
    const id = chapterIdForSpecies(sp);
    buckets.get(id)?.push(sp);
  }
  return CHAPTERS.map((chapter) => {
    const list = buckets.get(chapter.id) || [];
    const rarityCounts = buildRarityCounts(list);
    const grandTotal = Object.values(rarityCounts).reduce((s, v) => s + v.total, 0);
    const grandEarned = Object.values(rarityCounts).reduce((s, v) => s + v.earned, 0);
    return {
      chapter,
      species: list,
      earned: grandEarned,
      total: grandTotal,
      rarityCounts,
      count: list.length,
    };
  });
}

// Whole-catalog rarity strand for the top IncipitBand — aggregates every
// species's potion variants across the entire codex.
export function totalRarityCounts(species = []) {
  return buildRarityCounts(species);
}

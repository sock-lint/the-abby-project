// Frontispiece constants — shared by SigilFrontispiece, CosmeticChapter,
// CosmeticSigil, TrophySlot, StreakGlyph. Kept in a .js file so the
// non-component exports don't trip react-refresh/only-export-components.

/**
 * Four cosmetic chapters, one per slot. Letters are first-letter-of-slot
 * so the IlluminatedVersal drop-cap stays mnemonic (F for Frames, T for
 * Titles, B for Bindings/covers, P for Pet regalia). Rubric numerals
 * continue the §I–§IV codex convention from the Reliquary Codex.
 */
export const COSMETIC_CHAPTERS = [
  {
    slot: 'active_frame',
    rubric: '\u00a7I',
    letter: 'F',
    name: 'Frames',
    kicker: 'a border of renown',
  },
  {
    slot: 'active_title',
    rubric: '\u00a7II',
    letter: 'T',
    name: 'Titles',
    kicker: 'the name you bear',
  },
  {
    slot: 'active_theme',
    rubric: '\u00a7III',
    letter: 'B',
    name: 'Journal Covers',
    kicker: 'the binding of your tome',
  },
  {
    slot: 'active_pet_accessory',
    rubric: '\u00a7IV',
    letter: 'P',
    name: 'Pet Regalia',
    kicker: 'cloth for your companion',
  },
];

export const COSMETIC_CHAPTERS_BY_SLOT = Object.fromEntries(
  COSMETIC_CHAPTERS.map((c) => [c.slot, c]),
);

const RARITY_KEYS = ['common', 'uncommon', 'rare', 'epic', 'legendary'];
const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, epic: 3, legendary: 4 };

/**
 * Streak-tier ladder. `tier` feeds the gilt color via PROGRESS_TIER and
 * the size of the StreakFlame. Matches the milestone notifications
 * that fire from the backend (streak_days = 3/7/14/30/60/100) so the
 * visual reward aligns with the badge gating.
 */
export const STREAK_TIERS = [
  { min: 0,   flame: 'xs', tier: 'locked'   },
  { min: 1,   flame: 'sm', tier: 'nascent'  },
  { min: 7,   flame: 'md', tier: 'rising'   },
  { min: 30,  flame: 'lg', tier: 'cresting' },
  { min: 100, flame: 'xl', tier: 'gilded'   },
];

export function streakTier(days) {
  const d = Number(days) || 0;
  let chosen = STREAK_TIERS[0];
  for (const row of STREAK_TIERS) {
    if (d >= row.min) chosen = row;
  }
  return chosen;
}

/**
 * Merge owned cosmetics with the full catalog to produce a flat,
 * sort-stable list per slot. Each entry is
 * `{ item, owned: bool, equipped: bool }`. Equipped first, then owned
 * (by rarity ↑ then name), then unowned (by rarity ↑ then name).
 */
export function mergeSlotCosmetics(slot, owned, catalog, activeId) {
  const ownedList = Array.isArray(owned) ? owned : [];
  const catalogList = Array.isArray(catalog) ? catalog : [];
  const ownedIds = new Set(ownedList.map((x) => x.id));

  const entries = [];
  for (const item of ownedList) {
    entries.push({ item, owned: true, equipped: item.id === activeId });
  }
  const seenOwned = new Set(ownedList.map((x) => x.id));
  for (const item of catalogList) {
    if (!ownedIds.has(item.id) && !seenOwned.has(item.id)) {
      entries.push({ item, owned: false, equipped: false });
    }
  }
  return entries.sort((a, b) => {
    if (a.equipped && !b.equipped) return -1;
    if (!a.equipped && b.equipped) return 1;
    if (a.owned && !b.owned) return -1;
    if (!a.owned && b.owned) return 1;
    const ra = RARITY_ORDER[a.item.rarity] ?? 99;
    const rb = RARITY_ORDER[b.item.rarity] ?? 99;
    if (ra !== rb) return ra - rb;
    return (a.item.name || '').localeCompare(b.item.name || '');
  });
}

/**
 * Per-slot rarity distribution strand. Mirrors `rarityCounts` from the
 * Reliquary Codex but counts owned-vs-catalog-total rather than
 * earned-vs-all-badges.
 */
export function slotRarityCounts(entries) {
  const counts = RARITY_KEYS.reduce((acc, k) => {
    acc[k] = { earned: 0, total: 0 };
    return acc;
  }, {});
  for (const entry of entries ?? []) {
    const key = counts[entry.item.rarity] ? entry.item.rarity : 'common';
    counts[key].total += 1;
    if (entry.owned) counts[key].earned += 1;
  }
  return counts;
}

/**
 * Fallback hint used for un-owned cosmetic tiles. Uses `item.description`
 * when present, otherwise a rarity-flavored default ("drops at rare
 * rarity" etc.). Kept here so the three places that render sigils
 * (catalog, picker, slot) render the same copy.
 */
export function cosmeticLockHint(item) {
  if (!item) return '';
  if (item.description) return item.description;
  switch (item.rarity) {
    case 'legendary': return 'a legendary drop — exceedingly rare';
    case 'epic':      return 'an epic drop — rare';
    case 'rare':      return 'a rare drop';
    case 'uncommon':  return 'uncommon — earn from quests and milestones';
    default:          return 'earn from drops and daily tasks';
  }
}

export { RARITY_KEYS };

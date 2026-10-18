import { describe, it, expect } from 'vitest';
import {
  COSMETIC_CHAPTERS,
  COSMETIC_CHAPTERS_BY_SLOT,
  STREAK_TIERS,
  cosmeticLockHint,
  mergeSlotCosmetics,
  slotRarityCounts,
  streakTier,
} from './character.constants';

describe('character.constants', () => {
  describe('COSMETIC_CHAPTERS', () => {
    it('ships the two profile cosmetic chapters in order', () => {
      expect(COSMETIC_CHAPTERS).toHaveLength(2);
      expect(COSMETIC_CHAPTERS.map((c) => c.slot)).toEqual([
        'active_frame',
        'active_title',
      ]);
    });

    it('exports a slot \u2192 chapter lookup', () => {
      expect(COSMETIC_CHAPTERS_BY_SLOT.active_frame.name).toBe('Frames');
      expect(COSMETIC_CHAPTERS_BY_SLOT.active_pet_accessory).toBeUndefined();
    });
  });

  describe('streakTier', () => {
    it.each([
      [0, 'locked'],
      [1, 'nascent'],
      [3, 'nascent'],
      [7, 'rising'],
      [29, 'rising'],
      [30, 'cresting'],
      [99, 'cresting'],
      [100, 'gilded'],
      [500, 'gilded'],
    ])('%i days \u2192 %s', (days, tier) => {
      expect(streakTier(days).tier).toBe(tier);
    });

    it('handles non-numeric input by treating it as zero', () => {
      expect(streakTier(undefined).tier).toBe('locked');
      expect(streakTier('nope').tier).toBe('locked');
    });

    it('exposes matching flame size for every tier', () => {
      const flames = STREAK_TIERS.map((t) => t.flame);
      expect(flames).toContain('xs');
      expect(flames).toContain('xl');
    });
  });

  describe('mergeSlotCosmetics', () => {
    const catalog = [
      { id: 1, name: 'Bronze Frame', rarity: 'common' },
      { id: 2, name: 'Silver Frame', rarity: 'uncommon' },
      { id: 3, name: 'Gold Frame', rarity: 'rare' },
      { id: 4, name: 'Diamond Frame', rarity: 'legendary' },
    ];

    it('marks owned + equipped + places equipped first', () => {
      const owned = [
        { id: 1, name: 'Bronze Frame', rarity: 'common' },
        { id: 3, name: 'Gold Frame', rarity: 'rare' },
      ];
      const merged = mergeSlotCosmetics('active_frame', owned, catalog, 3);
      expect(merged.map((e) => [e.item.id, e.owned, e.equipped])).toEqual([
        [3, true, true],
        [1, true, false],
        [2, false, false],
        [4, false, false],
      ]);
    });

    it('places owned ahead of unowned and sorts by rarity then name', () => {
      const owned = [{ id: 2, name: 'Silver Frame', rarity: 'uncommon' }];
      const merged = mergeSlotCosmetics('active_frame', owned, catalog, null);
      expect(merged[0].item.id).toBe(2);
      expect(merged[0].owned).toBe(true);
      // Remaining are unowned, sorted by rarity ascending.
      expect(merged.slice(1).map((e) => e.item.id)).toEqual([1, 3, 4]);
    });

    it('tolerates missing arrays', () => {
      expect(mergeSlotCosmetics('active_frame', null, null, null)).toEqual([]);
    });
  });

  describe('slotRarityCounts', () => {
    it('sums owned/total per rarity', () => {
      const entries = [
        { item: { rarity: 'common' }, owned: true, equipped: false },
        { item: { rarity: 'common' }, owned: false, equipped: false },
        { item: { rarity: 'rare' }, owned: true, equipped: true },
      ];
      const counts = slotRarityCounts(entries);
      expect(counts.common).toEqual({ earned: 1, total: 2 });
      expect(counts.rare).toEqual({ earned: 1, total: 1 });
      expect(counts.legendary).toEqual({ earned: 0, total: 0 });
    });
  });

  describe('cosmeticLockHint', () => {
    it('prefers actual server acquisition paths over an item description', () => {
      expect(cosmeticLockHint({ description: 'A shiny frame.', acquisition_sources: [{ kind: 'challenge', name: 'Steady reader', path: '/quests?tab=trials' }] }))
        .toBe('Complete Steady reader to earn this.');
      expect(cosmeticLockHint({ acquisition_sources: [{ kind: 'drop', name: 'Homework', path: '/quests?tab=study' }] }))
        .toBe('Can drop from Homework.');
    });

    it('prefers item.description when present', () => {
      expect(cosmeticLockHint({ description: 'unlocks at level 10', rarity: 'common' }))
        .toBe('unlocks at level 10');
    });

    it('does not infer an earning path from rarity when no source is supplied', () => {
      expect(cosmeticLockHint({ rarity: 'legendary' })).toBe('Not yet owned');
      expect(cosmeticLockHint({ rarity: 'rare' })).toBe('Not yet owned');
      expect(cosmeticLockHint({})).toBe('Not yet owned');
    });

    it('returns empty string when no item is supplied', () => {
      expect(cosmeticLockHint(null)).toBe('');
    });
  });
});

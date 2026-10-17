import { describe, expect, it } from 'vitest';
import { companionRarity } from './rarity';
import { compareByRarityThenName } from '../pages/bestiary/party/party.constants';
import { totalRarityCounts } from '../pages/bestiary/codex/codex.constants';

describe('companion acquisition rarity', () => {
  it('uses the confirmed species tier for a Base companion at every growth stage', () => {
    const pet = { species: { rarity: 'legendary' }, potion: { rarity: 'common' } };
    expect(companionRarity(pet)).toBe('legendary');
    expect(companionRarity({ ...pet, growth_points: 100, evolved_to_mount: true })).toBe('legendary');
    expect(companionRarity({ rarity: 'rare', species: { rarity: 'rare' }, potion: { rarity: 'common' } })).toBe('rare');
  });

  it('keeps higher saved potion rarity and handles older responses', () => {
    expect(companionRarity({ species: { rarity: 'common' }, potion: { rarity: 'epic' } })).toBe('epic');
    expect(companionRarity({ potion: { rarity: 'rare' } })).toBe('rare');
    expect(companionRarity({})).toBe('common');
  });

  it('sorts rare species ahead of a less rare potion recolor', () => {
    const dragon = { species: { name: 'Dragon Spark', rarity: 'legendary' }, potion: { rarity: 'common' } };
    const saved = { species: { name: 'Wolf', rarity: 'common' }, potion: { rarity: 'epic' } };
    expect([saved, dragon].sort(compareByRarityThenName)).toEqual([dragon, saved]);
  });

  it('counts Base species acquisition rarity in the codex while preserving higher variants', () => {
    const counts = totalRarityCounts([
      { rarity: 'legendary', available_potions: [{ id: 1, rarity: 'common' }], owned_mount_potion_ids: [1] },
      { rarity: 'uncommon', available_potions: [{ id: 2, rarity: 'epic' }], owned_mount_potion_ids: [] },
    ]);
    expect(counts.legendary).toEqual({ earned: 1, total: 1 });
    expect(counts.epic).toEqual({ earned: 0, total: 1 });
    expect(counts.common.total).toBe(0);
  });
});

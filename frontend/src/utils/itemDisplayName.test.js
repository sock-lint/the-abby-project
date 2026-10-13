import { describe, expect, it } from 'vitest';
import { itemDisplayName } from './itemDisplayName';

describe('item display names', () => {
  it('uses current palette names for saved and legacy theme keys', () => {
    expect(itemDisplayName({ item_type: 'cosmetic_theme', name: 'Hyrule Day', metadata: { theme: 'hyrule' } })).toBe('Memory Meadow');
    expect(itemDisplayName({ item_type: 'cosmetic_theme', name: 'Summer', metadata: { theme: 'summer' } })).toBe('Honey Meadow');
  });
  it('preserves authored names for other items and unknown keepsakes', () => {
    expect(itemDisplayName({ item_type: 'cosmetic_title', name: 'My title', metadata: { theme: 'hyrule' } })).toBe('My title');
    expect(itemDisplayName({ item_type: 'cosmetic_theme', name: 'Earlier cover', metadata: { theme: 'earlier' } })).toBe('Earlier cover');
  });
});

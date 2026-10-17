import { describe, expect, it } from 'vitest';
import { itemDisplayName } from './itemDisplayName';

describe('item display names', () => {
  it('uses current palette names for saved and legacy theme keys', () => {
    for (const [theme, name] of Object.entries({
      hyrule: 'Memory Meadow', vigil: 'Twilight Meadow', sunlit: 'Honey Meadow',
      snowquill: 'Cloud Meadow', verdant: 'Clover Meadow', harvest: 'Peach Meadow',
      summer: 'Honey Meadow', winter: 'Cloud Meadow', spring: 'Clover Meadow', autumn: 'Peach Meadow',
    })) {
      expect(itemDisplayName({ item_type: 'cosmetic_theme', name: 'Earlier name', metadata: { theme } })).toBe(name);
    }
  });
  it('preserves authored names for other items and unknown keepsakes', () => {
    expect(itemDisplayName({ item_type: 'cosmetic_title', name: 'My title', metadata: { theme: 'hyrule' } })).toBe('My title');
    expect(itemDisplayName({ item_type: 'cosmetic_theme', name: 'Earlier cover', metadata: { theme: 'earlier' } })).toBe('Earlier cover');
  });
});

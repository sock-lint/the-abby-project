import { describe, expect, it } from 'vitest';
import { AVATAR_DEFAULTS, normalizeAvatarPreferences, sameAvatarPreferences } from './preferences';

const wardrobe = {
  headwear_style: 'crown-eve', mask_style: 'mask-undercover',
  bow_style: 'bow-vines', quiver_style: 'quiver-tale',
};

describe('saved Archer wardrobe preferences', () => {
  it('projects an older identity with no equipment instead of inventing a saved loadout', () => {
    expect(normalizeAvatarPreferences({ hair_style: 'hair-04', outfit: 'fire' })).toEqual({
      hair_style: 'hair-04', hair_color: 'dark', skin_tone: 'fair', outfit: 'fire',
      outfit_style: 'archer-01', face_style: 'face-01', head_style: 'head-02',
      headwear_style: 'none', mask_style: 'none', bow_style: 'none', quiver_style: 'none',
    });
  });

  it('retains independent supplied equipment and ignores unknown fields', () => {
    expect(normalizeAvatarPreferences({ ...wardrobe, inventory_id: 99 })).toEqual({ ...AVATAR_DEFAULTS, ...wardrobe });
    expect(normalizeAvatarPreferences({ headwear_style: 'helmet', mask_style: [], bow_style: false, quiver_style: 'missing' })).toMatchObject({
      headwear_style: 'none', mask_style: 'none', bow_style: 'none', quiver_style: 'none',
    });
  });

  it.each(Object.entries(wardrobe))('recognizes an unsaved change to %s', (key, value) => {
    expect(sameAvatarPreferences(AVATAR_DEFAULTS, { ...AVATAR_DEFAULTS, [key]: value })).toBe(false);
  });
});

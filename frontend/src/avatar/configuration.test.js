import { describe, expect, it } from 'vitest';
import { avatarPreviewPreferences } from './configuration';
import { AVATAR_DEFAULTS } from './preferences';
import { archerConfiguration, syntheticArcher, syntheticKnight } from '../pages/avatar-customize/catalog.fixtures';

describe('explicit Archer preview configuration adapter', () => {
  it('maps fit-bound shared items only at the existing renderer boundary', () => {
    const configuration = { ...archerConfiguration, accessories: { headwear: 'crown-eve', face_accessory: 'mask-undercover', left_hand: 'bow-greenhorn', right_hand: 'none', back: 'quiver-rook' } };
    expect(avatarPreviewPreferences(configuration, syntheticArcher)).toEqual({ ...AVATAR_DEFAULTS, headwear_style: 'crown-eve', mask_style: 'mask-undercover', bow_style: 'bow-greenhorn', quiver_style: 'quiver-rook' });
    expect(avatarPreviewPreferences(archerConfiguration, syntheticArcher)).toEqual(AVATAR_DEFAULTS);
  });
  it('never renders another base as Archer even when an adapter string is copied', () => {
    expect(avatarPreviewPreferences({ avatar_id: syntheticKnight.id, ...syntheticKnight.defaults }, { ...syntheticKnight, renderer_adapter: 'female-archer' })).toBeNull();
    expect(avatarPreviewPreferences(archerConfiguration, null)).toBeNull();
    expect(avatarPreviewPreferences(archerConfiguration, { ...syntheticArcher, renderer_adapter: 'missing' })).toBeNull();
  });
  it.each([
    (configuration) => { delete configuration.accessories.right_hand; },
    (configuration) => { configuration.accessories.extra = 'none'; },
    (configuration) => { configuration.accessories.left_hand = 'unreviewed-bow'; },
    (configuration) => { configuration.accessories.right_hand = 'sword-long'; },
    (configuration) => { delete configuration.appearance.face_style; },
    (configuration) => { configuration.appearance.hair_color = 'missing'; },
  ])('shows unavailable for incomplete or unsupported configuration', (change) => {
    const configuration = structuredClone(archerConfiguration);change(configuration);
    expect(avatarPreviewPreferences(configuration, syntheticArcher)).toBeNull();
  });
  it.each([undefined, null, 'bow-greenhorn', {}])('does not throw for malformed raw fit metadata', (item_ids) => {
    const configuration = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, left_hand: 'bow-greenhorn' } };
    expect(avatarPreviewPreferences(configuration, { ...syntheticArcher, accessory_bindings: { ...syntheticArcher.accessory_bindings, left_hand: { item_ids } } })).toBeNull();
  });
});

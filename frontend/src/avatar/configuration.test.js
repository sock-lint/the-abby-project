import { describe, expect, it } from 'vitest';
import { avatarPreviewPreferences, preparedAvatarDefinition } from './configuration';
import { AVATAR_DEFAULTS } from './preferences';
import { archerConfiguration, syntheticArcher, syntheticKnight } from '../pages/avatar-customize/catalog.fixtures';

describe('native prepared avatar definition', () => {
  it('describes only the prepared Archer and its known equipment bindings', () => {
    expect(preparedAvatarDefinition('female-archer')).toEqual({
      id: 'female-archer', label: 'Female Archer', renderer_adapter: 'female-archer',
      accessory_bindings: {
        headwear: { item_ids: ['crown-eve', 'hood-mystical'] },
        face_accessory: { item_ids: ['mask-undercover'] },
        left_hand: { item_ids: ['bow-greenhorn', 'bow-vines', 'bow-myth'] },
        back: { item_ids: ['quiver-angel', 'quiver-rook', 'quiver-tale'] },
        right_hand: { item_ids: [] },
      },
    });
  });

  it('renders a confirmed equipped Archer without a server catalog descriptor', () => {
    const configuration = {
      avatar_id: 'female-archer',
      appearance: { hair_style: 'hair-04', hair_color: 'grey', skin_tone: 'tan', outfit: 'fire', outfit_style: 'archer-03', face_style: 'face-03', head_style: 'head-01' },
      accessories: { headwear: 'hood-mystical', face_accessory: 'mask-undercover', left_hand: 'bow-myth', right_hand: 'none', back: 'quiver-tale' },
    };
    expect(avatarPreviewPreferences(configuration, preparedAvatarDefinition(configuration.avatar_id))).toEqual({
      ...configuration.appearance, headwear_style: 'hood-mystical', mask_style: 'mask-undercover', bow_style: 'bow-myth', quiver_style: 'quiver-tale',
    });
  });

  it.each([
    ['bow-greenhorn', 'quiver-rook'], ['bow-vines', 'quiver-angel'], ['bow-myth', 'quiver-tale'],
  ])('keeps shared equipment IDs %s and %s at the prepared renderer boundary', (bow, quiver) => {
    expect(syntheticKnight.accessory_bindings.left_hand.item_ids).toContain(bow);
    expect(syntheticKnight.accessory_bindings.back.item_ids).toContain(quiver);
    const configuration = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, left_hand: bow, back: quiver } };
    expect(avatarPreviewPreferences(configuration, preparedAvatarDefinition(configuration.avatar_id))).toEqual({
      ...AVATAR_DEFAULTS, bow_style: bow, quiver_style: quiver,
    });
  });

  it.each([undefined, null, '', 'synthetic-knight', 'female-archer '])('does not substitute Archer for an unprepared base %s', (avatarId) => {
    const definition = preparedAvatarDefinition(avatarId);
    expect(definition).toBeNull();
    expect(avatarPreviewPreferences({ ...archerConfiguration, avatar_id: avatarId }, definition)).toBeNull();
  });

  it.each([
    ['left_hand', 'shield-round'], ['right_hand', 'sword-long'], ['back', 'unreviewed-quiver'],
  ])('leaves unsupported %s equipment unavailable without a server catalog', (slot, itemId) => {
    const configuration = { ...archerConfiguration, accessories: { ...archerConfiguration.accessories, [slot]: itemId } };
    expect(avatarPreviewPreferences(configuration, preparedAvatarDefinition(configuration.avatar_id))).toBeNull();
  });

  it('does not share mutable bindings between fallback descriptors', () => {
    const first = preparedAvatarDefinition('female-archer');
    first.accessory_bindings.left_hand.item_ids.push('unreviewed-bow');
    const next = preparedAvatarDefinition('female-archer');
    expect(next.accessory_bindings.left_hand.item_ids).not.toContain('unreviewed-bow');
    expect(syntheticArcher.accessory_bindings.left_hand.item_ids).toEqual(next.accessory_bindings.left_hand.item_ids);
  });
});

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

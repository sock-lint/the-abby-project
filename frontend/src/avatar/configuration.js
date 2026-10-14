import { AVATAR_OPTIONS } from './preferences';

const APPEARANCE = ['hair_style', 'hair_color', 'skin_tone', 'outfit', 'outfit_style', 'face_style', 'head_style'];
const LEGACY_SLOTS = { headwear: 'headwear_style', face_accessory: 'mask_style', left_hand: 'bow_style', back: 'quiver_style' };
const SHARED_SLOTS = [...Object.keys(LEGACY_SLOTS), 'right_hand'];
const record = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);

// This is the explicit renderer boundary for the prepared Archer release.
// Catalog controls and saved shared equipment do not depend on this mapping.
export function avatarPreviewPreferences(configuration, avatarDefinition) {
  if (avatarDefinition?.id !== 'female-archer' || avatarDefinition.renderer_adapter !== 'female-archer'
    || configuration?.avatar_id !== avatarDefinition.id || !record(configuration.appearance) || !record(configuration.accessories)
    || Object.keys(configuration.appearance).length !== APPEARANCE.length
    || Object.keys(configuration.accessories).length !== SHARED_SLOTS.length
    || SHARED_SLOTS.some((slot) => !Object.hasOwn(configuration.accessories, slot))) return null;
  const preferences = {};
  for (const key of APPEARANCE) {
    const value = configuration.appearance[key];
    if (!AVATAR_OPTIONS[key].some((choice) => choice.value === value)) return null;
    preferences[key] = value;
  }
  for (const [slot, key] of Object.entries(LEGACY_SLOTS)) {
    const value = configuration.accessories[slot];
    if (!AVATAR_OPTIONS[key].some((choice) => choice.value === value)
      || (value !== 'none' && (!Array.isArray(avatarDefinition.accessory_bindings?.[slot]?.item_ids)
        || !avatarDefinition.accessory_bindings[slot].item_ids.includes(value)))) return null;
    preferences[key] = value;
  }
  if (configuration.accessories.right_hand !== 'none'
    || Object.entries(configuration.accessories).some(([slot, value]) => !Object.hasOwn(LEGACY_SLOTS, slot) && value !== 'none')) return null;
  return preferences;
}

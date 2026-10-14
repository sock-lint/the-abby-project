// Synthetic registries exercise cross-pack compatibility; no additional
// avatar or paid art is offered by the real application catalog.
const slots = [
  ['headwear', 'Headwear'], ['face_accessory', 'Face accessory'], ['left_hand', 'Weapon'],
  ['right_hand', 'Right hand accessory'], ['back', 'Back accessory'],
];
const items = {
  'crown-eve': 'Eve crown', 'hood-mystical': 'Mystical hood', 'mask-undercover': 'Undercover mask',
  'bow-greenhorn': 'Greenhorn bow', 'bow-vines': 'Vines bow', 'bow-myth': 'Myth bow',
  'quiver-angel': 'Angel quiver', 'quiver-rook': 'Rook quiver', 'quiver-tale': 'Tale quiver',
  'sword-long': 'Long sword', 'shield-round': 'Round shield',
};
const appearance = {
  hair_style: ['hair-01', 'hair-04'], hair_color: ['dark', 'grey'], skin_tone: ['fair', 'tan'],
  outfit: ['nature', 'fire'], outfit_style: ['archer-01', 'archer-03'], face_style: ['face-01', 'face-03'], head_style: ['head-02', 'head-01'],
};
const appearanceLabels = { hair_style: 'Hair style', hair_color: 'Hair color', skin_tone: 'Skin tone', outfit: 'Color', outfit_style: 'Outfit', face_style: 'Face', head_style: 'Ears' };
const archerBindings = { headwear: ['crown-eve', 'hood-mystical'], face_accessory: ['mask-undercover'], left_hand: ['bow-greenhorn', 'bow-vines', 'bow-myth'], right_hand: [], back: ['quiver-angel', 'quiver-rook', 'quiver-tale'] };
function base(id, label, renderer_adapter, appearanceChoices, bindings, presets = []) {
  return {
    id, label, renderer_adapter,
    defaults: { appearance: Object.fromEntries(Object.entries(appearanceChoices).map(([key, values]) => [key, values[0]])), accessories: Object.fromEntries(slots.map(([id]) => [id, 'none'])) },
    groups: [
      { id: 'identity', label: 'Appearance', fields: Object.entries(appearanceChoices).map(([key, values]) => ({ key, label: appearanceLabels[key] || key, choices: values.map((value) => ({ value, label: value })) })) },
      { id: 'wardrobe', label: 'Wardrobe', fields: slots.map(([key, label]) => ({ key, label, accessory_slot: key, choices: [{ value: 'none', label: 'None' }, ...bindings[key].map((value) => ({ value, accessory_id: value }))] })) },
    ],
    accessory_bindings: Object.fromEntries(slots.map(([slot]) => [slot, { item_ids: bindings[slot], attachment: bindings[slot].length ? `synthetic-${slot}` : null, legacy_preference_key: null }])),
    presets,
  };
}
export const syntheticArcher = base('female-archer', 'Female Archer', 'female-archer', appearance, archerBindings, [
  { id: 'fire', label: 'Fire', appearance: { outfit: 'fire' }, accessories: { headwear: 'crown-eve', left_hand: 'bow-myth', back: 'quiver-tale' } },
]);
export const syntheticKnight = base('synthetic-knight', 'Synthetic Knight', 'synthetic-knight', { armor_style: ['steel', 'blue'], crest_style: ['none', 'lion'] }, {
  headwear: ['crown-eve'], face_accessory: ['mask-undercover'], left_hand: ['bow-greenhorn', 'bow-vines', 'bow-myth', 'shield-round'], right_hand: ['sword-long'], back: ['quiver-angel', 'quiver-rook', 'quiver-tale'],
});
export const syntheticCatalog = {
  schema_version: 1, default_avatar_id: syntheticArcher.id,
  accessory_slots: slots.map(([id, label]) => ({ id, label })),
  accessories: Object.fromEntries(Object.entries(items).map(([id, label]) => [id, { label, source_pack: id.startsWith('sword') || id.startsWith('shield') ? 'synthetic-knight-source' : 'synthetic-archer-source' }])),
  avatars: [syntheticArcher, syntheticKnight],
};
export const archerConfiguration = { avatar_id: syntheticArcher.id, ...structuredClone(syntheticArcher.defaults) };

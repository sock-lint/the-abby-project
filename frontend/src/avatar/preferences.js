export const AVATAR_DEFAULTS = Object.freeze({
  hair_style: 'hair-01',
  hair_color: 'dark',
  skin_tone: 'fair',
  outfit: 'nature',
  outfit_style: 'archer-01',
  face_style: 'face-01',
  head_style: 'head-02',
  headwear_style: 'none',
  mask_style: 'none',
  bow_style: 'none',
  quiver_style: 'none',
});

export const AVATAR_OPTIONS = Object.freeze({
  hair_style: [
    { value: 'hair-01', label: 'Swept' },
    { value: 'hair-02', label: 'Bob' },
    { value: 'hair-03', label: 'Ponytail' },
    { value: 'hair-04', label: 'Side part' },
  ],
  hair_color: [
    { value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' },
    { value: 'brown', label: 'Brown' }, { value: 'orange', label: 'Orange' }, { value: 'grey', label: 'Grey' },
  ],
  skin_tone: [{ value: 'fair', label: 'Fair' }, { value: 'tan', label: 'Tan' }],
  outfit: [
    { value: 'nature', label: 'Nature' },
    { value: 'aqua', label: 'Aqua' },
    { value: 'fire', label: 'Fire' },
    { value: 'dark', label: 'Dark' },
  ],
  outfit_style: [
    { value: 'archer-01', label: 'Outfit 1' },
    { value: 'archer-02', label: 'Outfit 2' },
    { value: 'archer-03', label: 'Outfit 3' },
  ],
  face_style: [
    { value: 'face-01', label: 'Face 1' },
    { value: 'face-02', label: 'Face 2' },
    { value: 'face-03', label: 'Face 3' },
  ],
  head_style: [
    { value: 'head-01', label: 'Rounded' },
    { value: 'head-02', label: 'Pointed' },
  ],
  headwear_style: [
    { value: 'none', label: 'None' },
    { value: 'crown-eve', label: 'Eve crown' },
    { value: 'hood-mystical', label: 'Mystical hood' },
  ],
  mask_style: [{ value: 'none', label: 'None' }, { value: 'mask-undercover', label: 'Undercover' }],
  bow_style: [
    { value: 'none', label: 'None' }, { value: 'bow-greenhorn', label: 'Greenhorn' },
    { value: 'bow-vines', label: 'Vines' }, { value: 'bow-myth', label: 'Myth' },
  ],
  quiver_style: [
    { value: 'none', label: 'None' }, { value: 'quiver-angel', label: 'Angel' },
    { value: 'quiver-rook', label: 'Rook' }, { value: 'quiver-tale', label: 'Tale' },
  ],
});

export const AVATAR_WARDROBE_PRESETS = Object.freeze([
  { label: 'Aqua', preferences: { outfit: 'aqua', headwear_style: 'hood-mystical', mask_style: 'none', bow_style: 'bow-vines', quiver_style: 'quiver-angel' } },
  { label: 'Nature', preferences: { outfit: 'nature', headwear_style: 'none', mask_style: 'mask-undercover', bow_style: 'bow-greenhorn', quiver_style: 'quiver-rook' } },
  { label: 'Fire', preferences: { outfit: 'fire', headwear_style: 'crown-eve', mask_style: 'none', bow_style: 'bow-myth', quiver_style: 'quiver-tale' } },
  { label: 'Dark', preferences: { outfit: 'dark', headwear_style: 'hood-mystical', mask_style: 'mask-undercover', bow_style: 'bow-myth', quiver_style: 'quiver-tale' } },
]);

export function normalizeAvatarPreferences(preferences) {
  return Object.fromEntries(Object.entries(AVATAR_DEFAULTS).map(([key, value]) => [
    key,
    AVATAR_OPTIONS[key].some((option) => option.value === preferences?.[key]) ? preferences[key] : value,
  ]));
}

export function sameAvatarPreferences(left, right) {
  return Object.keys(AVATAR_DEFAULTS).every((key) => left[key] === right[key]);
}

export const AVATAR_DEFAULTS = Object.freeze({
  hair_style: 'hair-01',
  hair_color: 'dark',
  skin_tone: 'fair',
  outfit: 'nature',
  outfit_style: 'archer-01',
  face_style: 'face-01',
  head_style: 'head-02',
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
});

export function normalizeAvatarPreferences(preferences) {
  return Object.fromEntries(Object.entries(AVATAR_DEFAULTS).map(([key, value]) => [
    key,
    AVATAR_OPTIONS[key].some((option) => option.value === preferences?.[key]) ? preferences[key] : value,
  ]));
}

export function sameAvatarPreferences(left, right) {
  return Object.keys(AVATAR_DEFAULTS).every((key) => left[key] === right[key]);
}

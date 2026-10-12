export const AVATAR_DEFAULTS = Object.freeze({
  hair_style: 'hair-01',
  hair_color: 'dark',
  skin_tone: 'fair',
  outfit: 'nature',
});

export const AVATAR_OPTIONS = Object.freeze({
  hair_style: [
    { value: 'hair-01', label: 'Swept' },
    { value: 'hair-02', label: 'Bob' },
    { value: 'hair-03', label: 'Ponytail' },
    { value: 'hair-04', label: 'Side part' },
  ],
  hair_color: [{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }],
  skin_tone: [{ value: 'fair', label: 'Fair' }, { value: 'tan', label: 'Tan' }],
  outfit: [
    { value: 'nature', label: 'Nature' },
    { value: 'aqua', label: 'Aqua' },
    { value: 'fire', label: 'Fire' },
    { value: 'dark', label: 'Dark' },
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

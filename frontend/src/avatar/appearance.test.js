import { describe, expect, it } from 'vitest';
import { resolveAvatarAppearance } from './appearance';
import { AVATAR_DEFAULTS, normalizeAvatarPreferences } from './preferences';

const manifest = {
  schema_version: 1,
  models: { archer: { file: 'archer.glb', idle_clip: null } },
  parts: { body: 'Body', head: 'Head', face: 'Face', hair: { 'hair-01': 'Hair 01', 'hair-03': 'Hair 03' } },
  textures: {
    outfit: { 'fair:nature': 'fair-nature.png', 'tan:fire': 'tan-fire.png' },
    hair: { dark: 'hair-dark.png', light: 'hair-light.png' },
    face: { dark: 'face-dark.png', light: 'face-light.png' },
  },
};
const files = ['archer.glb', 'fair-nature.png', 'tan-fire.png', 'hair-dark.png', 'hair-light.png', 'face-dark.png', 'face-light.png'];
const urls = Object.fromEntries(files.map((file) => [`./licensed/${file}`, `/assets/${file}`]));

describe('owned Archer appearance', () => {
  it('selects the exact supplied body, hair and face texture variants', () => {
    const appearance = resolveAvatarAppearance({ hair_style: 'hair-03', hair_color: 'light', skin_tone: 'tan', outfit: 'fire' }, manifest, urls);
    expect(appearance.hairStyle).toBe('hair-03');
    expect(appearance.textures).toEqual({ body: '/assets/tan-fire.png', hair: '/assets/hair-light.png', face: '/assets/face-light.png' });
    expect(appearance.idleClip).toBeNull();
  });

  it('requires the selected supplied parts and texture files before rendering', () => {
    expect(resolveAvatarAppearance({ ...AVATAR_DEFAULTS, hair_style: 'hair-04' }, manifest, urls)).toBeNull();
    expect(resolveAvatarAppearance(AVATAR_DEFAULTS, manifest, { ...urls, './licensed/face-dark.png': undefined })).toBeNull();
    expect(resolveAvatarAppearance(AVATAR_DEFAULTS, null, urls)).toBeNull();
  });

  it('uses stable defaults for missing or unsupported saved fields', () => {
    expect(normalizeAvatarPreferences({ hair_style: 'unknown', outfit: 'unknown', arbitrary: 'secret' })).toEqual(AVATAR_DEFAULTS);
  });
});

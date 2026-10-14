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

// Synthetic runtime contracts; these do not establish purchased-art readiness.
const expandedManifest = {
  schema_version: 2,
  models: Object.fromEntries(['archer-01', 'archer-02', 'archer-03'].map((style) => [style, { file: `${style}.glb`, idle_clip: 'Idle' }])),
  parts: {
    body: 'Body',
    head: { 'head-01': 'Head Rounded', 'head-02': 'Head Pointed' }, face: 'Face',
    hair: Object.fromEntries(['hair-01', 'hair-02', 'hair-03', 'hair-04'].map((key) => [key, key])),
  },
  textures: {
    outfit: Object.fromEntries(['archer-01', 'archer-02', 'archer-03'].flatMap((style) =>
      ['fair', 'tan'].flatMap((skin) => ['aqua', 'nature', 'fire', 'dark'].map((outfit) =>
        [`${style}:${skin}:${outfit}`, `${style}-${skin}-${outfit}.png`])))),
    hair: Object.fromEntries(['light', 'dark', 'brown', 'orange', 'grey'].map((color) => [color, `hair-${color}.png`])),
    face: Object.fromEntries(['face-01', 'face-02', 'face-03'].flatMap((face) =>
      ['light', 'dark', 'brown', 'orange', 'grey'].map((color) => [`${face}:${color}`, `${face}-${color}.png`]))),
  },
};
const expandedUrls = Object.fromEntries([
  ...Object.values(expandedManifest.models).map((model) => model.file), ...Object.values(expandedManifest.textures).flatMap(Object.values),
].map((file) => [`./licensed/${file}`, `/assets/${file}`]));
const wardrobeStyles = {
  headwear: ['crown-eve', 'hood-mystical'], mask: ['mask-undercover'],
  bow: ['bow-greenhorn', 'bow-vines', 'bow-myth'], quiver: ['quiver-angel', 'quiver-rook', 'quiver-tale'],
};
const wardrobeManifest = {
  ...expandedManifest, schema_version: 3,
  parts: { ...expandedManifest.parts, wardrobe: {
    hair_for_hat: 'Hair for hat',
    ...Object.fromEntries(Object.entries(wardrobeStyles).map(([slot, styles]) => [slot, Object.fromEntries(styles.map((style) => [style, style]))])),
  } },
  textures: { ...expandedManifest.textures, wardrobe: Object.fromEntries(Object.values(wardrobeStyles).flat().flatMap((style) =>
    ['aqua', 'nature', 'fire', 'dark'].map((palette) => [`${style}:${palette}`, ['bow-greenhorn', 'quiver-rook'].includes(style) ? 'neutral.png' : `wardrobe-${palette}.png`]))),
  },
};
const wardrobeUrls = { ...expandedUrls, ...Object.fromEntries(['neutral.png', ...['aqua', 'nature', 'fire', 'dark'].map((palette) => `wardrobe-${palette}.png`)]
  .map((file) => [`./licensed/${file}`, `/assets/${file}`])) };

describe('owned Archer appearance', () => {
  it('requires a wardrobe-capable release instead of silently dropping saved equipment', () => {
    for (const source of [manifest, expandedManifest]) {
      for (const [slot, styles] of Object.entries(wardrobeStyles)) {
        expect(resolveAvatarAppearance({ [`${slot}_style`]: styles[0] }, source, { ...urls, ...expandedUrls })).toBeNull();
      }
    }
  });

  it('resolves every supplied wardrobe piece in each palette with verified neutral aliases', () => {
    for (const outfit of ['aqua', 'nature', 'fire', 'dark']) {
      for (const [slot, styles] of Object.entries(wardrobeStyles)) {
        for (const style of styles) {
          const selected = resolveAvatarAppearance({ outfit, [`${slot}_style`]: style, hair_style: 'hair-04' }, wardrobeManifest, wardrobeUrls);
          expect(selected).toMatchObject({ hairStyle: 'hair-04', wardrobe: { [slot]: style }, idleClip: 'Idle' });
          expect(selected.textures[slot]).toBe(['bow-greenhorn', 'quiver-rook'].includes(style) ? '/assets/neutral.png' : `/assets/wardrobe-${outfit}.png`);
          expect(Object.keys(selected.textures)).toEqual(['body', 'hair', 'face', slot]);
        }
      }
    }
    expect(resolveAvatarAppearance({}, wardrobeManifest, wardrobeUrls)).toMatchObject({
      wardrobe: { headwear: 'none', mask: 'none', bow: 'none', quiver: 'none' },
      textures: { body: '/assets/archer-01-fair-nature.png', hair: '/assets/hair-dark.png', face: '/assets/face-01-dark.png' },
    });
  });

  it('requires the selected wardrobe texture and the complete wardrobe mesh contract', () => {
    expect(resolveAvatarAppearance({ headwear_style: 'hood-mystical' }, wardrobeManifest, { ...wardrobeUrls, './licensed/wardrobe-nature.png': undefined })).toBeNull();
    for (const wardrobe of [undefined, { ...wardrobeManifest.parts.wardrobe, hair_for_hat: undefined }, { ...wardrobeManifest.parts.wardrobe, bow: {} }]) {
      expect(resolveAvatarAppearance({}, { ...wardrobeManifest, parts: { ...wardrobeManifest.parts, wardrobe } }, wardrobeUrls)).toBeNull();
    }
  });
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

  it('resolves every expanded identity to its exact body, palette and matching brows', () => {
    let resolved = 0;
    for (const outfit_style of ['archer-01', 'archer-02', 'archer-03']) {
      for (const skin_tone of ['fair', 'tan']) {
        for (const outfit of ['aqua', 'nature', 'fire', 'dark']) {
          for (const hair_color of ['light', 'dark', 'brown', 'orange', 'grey']) {
            for (const hair_style of ['hair-01', 'hair-02', 'hair-03', 'hair-04']) {
              for (const face_style of ['face-01', 'face-02', 'face-03']) {
                for (const head_style of ['head-01', 'head-02']) {
                  const appearance = resolveAvatarAppearance({ outfit_style, skin_tone, outfit, hair_color, hair_style, face_style, head_style }, expandedManifest, expandedUrls);
                  expect(appearance).toMatchObject({
                    url: `/assets/${outfit_style}.glb`, outfitStyle: outfit_style, hairStyle: hair_style, headStyle: head_style, idleClip: 'Idle',
                    textures: {
                      body: `/assets/${outfit_style}-${skin_tone}-${outfit}.png`,
                      hair: `/assets/hair-${hair_color}.png`, face: `/assets/${face_style}-${hair_color}.png`,
                    },
                  });
                  resolved += 1;
                }
              }
            }
          }
        }
      }
    }
    expect(resolved).toBe(2880);
  });

  it('preserves legacy appearances without substituting unsupported expanded choices', () => {
    expect(resolveAvatarAppearance({ hair_color: 'brown' }, manifest, urls)).toBeNull();
    expect(resolveAvatarAppearance({ outfit_style: 'archer-02' }, manifest, urls)).toBeNull();
    expect(resolveAvatarAppearance({ face_style: 'face-02' }, manifest, urls)).toBeNull();
    expect(resolveAvatarAppearance({ head_style: 'head-01' }, manifest, urls)).toBeNull();
    expect(resolveAvatarAppearance({}, manifest, urls)).toMatchObject({ outfitStyle: 'archer-01', idleClip: null });
  });

  it('requires the selected expanded mesh, texture and accepted Idle declaration', () => {
    const preferences = { outfit_style: 'archer-02', hair_color: 'grey' };
    const withoutBody = { ...expandedManifest, models: { 'archer-01': expandedManifest.models['archer-01'] } };
    expect(resolveAvatarAppearance(preferences, withoutBody, expandedUrls)).toBeNull();
    expect(resolveAvatarAppearance(preferences, { ...expandedManifest, parts: { ...expandedManifest.parts, head: { 'head-01': 'Head Rounded' } } }, expandedUrls)).toBeNull();
    expect(resolveAvatarAppearance(preferences, expandedManifest, { ...expandedUrls, './licensed/face-01-grey.png': undefined })).toBeNull();
    for (const idle_clip of [undefined, null, 'Walk']) {
      expect(resolveAvatarAppearance(preferences, { ...expandedManifest, models: { ...expandedManifest.models, 'archer-02': { file: 'archer-02.glb', idle_clip } } }, expandedUrls)).toBeNull();
    }
  });
});

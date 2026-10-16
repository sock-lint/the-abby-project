import { resolveConfiguration, validateManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';
import { normalizeAvatarPreferences } from './preferences';

const manifests = import.meta.glob('./shared/**/manifest.json', { eager: true, import: 'default' });
const files = import.meta.glob('./shared/**/*.{glb,png}', { eager: true, query: '?url', import: 'default' });
const FAMILY = 'meshtint-female-archer-pack-01';
const COLORS = { dark: 'black', light: 'blonde', brown: 'brown', orange: 'orange', grey: 'grey' };

/** Resolve only the checked-in pin. A different staged release is never selected
 * merely because its files happen to be present in the build directory. */
export function stagedArcherRelease(available = manifests, urls = files, lock = assetLock) {
  const pin = lock.releases?.find((entry) => entry.family_id === FAMILY);
  if (!pin) return null;
  const prefix = `./shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  if (!release || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateManifest(release); } catch { return null; }
  const resolveUrl = (file) => urls[`${prefix}${file}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { pipeline: 'abby-assets', release, resolveUrl };
}

/** Map the application's existing server-confirmed IDs to the shared catalog.
 * This adapter changes presentation only; Django still validates saved choices. */
export function sharedAvatarConfiguration(preferences, release) {
  const selected = normalizeAvatarPreferences(preferences);
  const slots = {};
  const paletteItem = (style, neutral) => style === neutral ? style : `${style}-${selected.outfit}`;
  if (selected.headwear_style !== 'none') slots.head = paletteItem(selected.headwear_style);
  if (selected.mask_style !== 'none') slots['face-accessory'] = paletteItem(selected.mask_style);
  if (selected.bow_style !== 'none') slots['left-hand'] = paletteItem(selected.bow_style, 'bow-greenhorn');
  if (selected.quiver_style !== 'none') slots.back = paletteItem(selected.quiver_style, 'quiver-rook');
  return {
    schema_version: 2,
    family_id: release.family_id,
    appearance: {
      body: selected.outfit_style.slice(-2), skin: selected.skin_tone, outfit: selected.outfit,
      head: selected.head_style.slice(-2), hair_style: selected.hair_style.slice(-2),
      hair_color: COLORS[selected.hair_color], face_style: selected.face_style.slice(-2),
      face_color: COLORS[selected.hair_color],
    },
    slots,
    emission_enabled: false,
  };
}

export function resolveSharedAvatarAppearance(preferences, staged) {
  try {
    const configuration = sharedAvatarConfiguration(preferences, staged.release);
    const resolved = resolveConfiguration(staged.release, configuration);
    const selected = normalizeAvatarPreferences(preferences);
    return {
      ...staged, configuration: resolved.configuration,
      url: staged.resolveUrl(resolved.variant.file), idleClip: staged.release.animations.actions.idle,
      rotationY: 0, textures: {}, hairStyle: selected.hair_style, headStyle: selected.head_style,
      outfitStyle: selected.outfit_style,
      wardrobe: Object.fromEntries(['headwear', 'mask', 'bow', 'quiver'].map((slot) => [slot, selected[`${slot}_style`]])),
    };
  } catch { return null; }
}

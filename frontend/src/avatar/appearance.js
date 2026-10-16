import { AVATAR_OPTIONS, normalizeAvatarPreferences } from './preferences';
import { resolveSharedAvatarAppearance, stagedArcherRelease } from './sharedRelease';

const manifests = import.meta.glob('./licensed/manifest.json', { eager: true, import: 'default' });
const assets = import.meta.glob('./licensed/*.{glb,png}', { eager: true, query: '?url', import: 'default' });

export function resolveAvatarAppearance(preferences, source = stagedArcherRelease() || manifests['./licensed/manifest.json'], urls = assets) {
  if (source?.pipeline === 'abby-assets') return resolveSharedAvatarAppearance(preferences, source);
  if (![1, 2, 3].includes(source?.schema_version)) return null;
  const selected = normalizeAvatarPreferences(preferences);
  const expanded = source.schema_version >= 2;
  const hasWardrobe = source.schema_version === 3;
  const wardrobe = Object.fromEntries(['headwear', 'mask', 'bow', 'quiver'].map((slot) => [slot, selected[`${slot}_style`]]));
  if (!hasWardrobe && Object.values(wardrobe).some((style) => style !== 'none')) return null;
  if (hasWardrobe && (!source.parts?.wardrobe?.hair_for_hat || Object.keys(wardrobe).some((slot) =>
    AVATAR_OPTIONS[`${slot}_style`].some(({ value }) => value !== 'none' && !source.parts.wardrobe[slot]?.[value])))) return null;
  // An older staged release can still show its original appearances, but it
  // must not depict a different body, face or hair color than the saved selection.
  if (!expanded && (selected.outfit_style !== 'archer-01' || selected.face_style !== 'face-01'
    || selected.head_style !== 'head-02' || !['light', 'dark'].includes(selected.hair_color))) return null;
  const model = expanded ? source.models?.[selected.outfit_style] : source.models?.archer;
  if (expanded && model?.idle_clip !== 'Idle') return null;
  const outfitKey = `${expanded ? `${selected.outfit_style}:` : ''}${selected.skin_tone}:${selected.outfit}`;
  const faceKey = `${expanded ? `${selected.face_style}:` : ''}${selected.hair_color}`;
  const files = {
    model: model?.file,
    body: source.textures?.outfit?.[outfitKey],
    hair: source.textures?.hair?.[selected.hair_color],
    face: source.textures?.face?.[faceKey],
    ...(hasWardrobe ? Object.fromEntries(Object.entries(wardrobe).filter(([, style]) => style !== 'none')
      .map(([slot, style]) => [slot, source.textures?.wardrobe?.[`${style}:${selected.outfit}`]])) : {}),
  };
  const resolved = Object.fromEntries(Object.entries(files).map(([key, file]) => [key, file && urls[`./licensed/${file}`]]));
  if (Object.values(resolved).some((url) => !url)
    || !source.parts?.body || !(expanded ? source.parts?.head?.[selected.head_style] : source.parts?.head)
    || !source.parts?.face || !source.parts?.hair?.[selected.hair_style]) return null;
  return {
    url: resolved.model,
    idleClip: model.idle_clip || null,
    rotationY: model.rotation_y || 0,
    parts: source.parts,
    hairStyle: selected.hair_style,
    outfitStyle: selected.outfit_style,
    headStyle: selected.head_style,
    wardrobe: hasWardrobe ? wardrobe : null,
    textures: Object.fromEntries(Object.entries(resolved).filter(([key]) => key !== 'model')),
  };
}

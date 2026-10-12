import { normalizeAvatarPreferences } from './preferences';

const manifests = import.meta.glob('./licensed/manifest.json', { eager: true, import: 'default' });
const assets = import.meta.glob('./licensed/*.{glb,png}', { eager: true, query: '?url', import: 'default' });

export function resolveAvatarAppearance(preferences, source = manifests['./licensed/manifest.json'], urls = assets) {
  if (source?.schema_version !== 1) return null;
  const model = source.models?.archer;
  const selected = normalizeAvatarPreferences(preferences);
  const files = {
    model: model?.file,
    body: source.textures?.outfit?.[`${selected.skin_tone}:${selected.outfit}`],
    hair: source.textures?.hair?.[selected.hair_color],
    face: source.textures?.face?.[selected.hair_color],
  };
  const resolved = Object.fromEntries(Object.entries(files).map(([key, file]) => [key, file && urls[`./licensed/${file}`]]));
  if (Object.values(resolved).some((url) => !url)
    || !source.parts?.body || !source.parts?.head || !source.parts?.face || !source.parts?.hair?.[selected.hair_style]) return null;
  return {
    url: resolved.model,
    idleClip: model.idle_clip || null,
    rotationY: model.rotation_y || 0,
    parts: source.parts,
    hairStyle: selected.hair_style,
    textures: { body: resolved.body, hair: resolved.hair, face: resolved.face },
  };
}

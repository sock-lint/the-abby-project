import { validateAssetPackManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';
import { birdStage } from './birdEvolution';
export { birdStage, BIRD_STAGES } from './birdEvolution';

const manifests = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, import: 'default' });
const manifestUrls = import.meta.glob('../avatar/shared/**/manifest.json', { eager: true, query: '?url', import: 'default' });
const files = import.meta.glob('../avatar/shared/**/*.{glb,png}', { eager: true, query: '?url', import: 'default' });
export const BIRD_FAMILY = 'meshtint-bird-evolution';

/** Stable refetches replace response objects, not the immutable runtime pack.
 * Include resolved payload URLs so a real transport/release change still loads
 * a new independently owned instance. Callback identity is not a resource key. */
export function birdPlaybackIdentity(appearance) {
  return JSON.stringify([
    appearance.key, appearance.manifestUrl, appearance.manifestSha256, appearance.url,
    (appearance.release?.files || []).map((file) => [file.path, appearance.resolveUrl(file.path)]),
  ]);
}

/** Only the exact checked-in release pin can supply an owned bird appearance. */
export function stagedBirdRelease(available = manifests, urls = files, lock = assetLock, indexes = manifestUrls) {
  const pin = lock.releases?.find((entry) => entry.family_id === BIRD_FAMILY);
  if (!pin) return null;
  const prefix = `../avatar/shared/${pin.directory}/`;
  const release = available[`${prefix}manifest.json`];
  const manifestUrl = indexes[`${prefix}manifest.json`];
  if (!release || !manifestUrl || release.family_id !== pin.family_id || release.release_version !== pin.release_version) return null;
  try { validateAssetPackManifest(release); } catch { return null; }
  const resolveUrl = (file) => urls[`${prefix}${file}`];
  if (release.files.some((file) => !resolveUrl(file.path))) return null;
  return { release, resolveUrl, manifestUrl, manifestSha256: pin.manifest_sha256 };
}

export function birdMotions(release, stage, resolveUrl) {
  const asset = release.assets.find((entry) => entry.id === stage);
  return (asset?.variants || []).flatMap((variant) => Object.entries(variant.animations?.actions || {}).map(([action, clip]) => {
    const metadata = variant.animations.clips.find((entry) => entry.name === clip);
    return {
      id: variant.id, action, label: variant.label, clip, url: resolveUrl(variant.file),
      loop: metadata.loop, rootMotion: metadata.root_motion, duration: metadata.duration,
    };
  }));
}

export function resolveSharedBirdAppearance(creature, kind = 'pet', staged = stagedBirdRelease()) {
  const stage = birdStage(creature, kind);
  return appearanceForStage(stage, staged);
}

export function resolveSharedBirdPreviewAppearance(item, stage, staged = stagedBirdRelease()) {
  if (item?.slug !== 'chick-egg' || item.item_type !== 'egg' || item.pet_species_slug !== 'chick' || item.metadata?.species !== 'chick') return null;
  return appearanceForStage({ baby: 'chick', middle: 'fledgling', grown: 'bird' }[stage], staged);
}

function appearanceForStage(stage, staged) {
  if (!stage || !staged) return null;
  const asset = staged.release.assets.find((entry) => entry.id === stage);
  const idle = asset?.variants.find((entry) => entry.id === asset.default_variant);
  if (!idle) return null;
  const motions = birdMotions(staged.release, stage, staged.resolveUrl);
  const aliases = { play: stage === 'bird' ? 'fly' : stage === 'fledgling' ? 'walk' : 'jump', left: 'turn_left', right: 'turn_right' };
  return {
    ...staged, pipeline: 'abby-assets-bird', key: stage, url: staged.resolveUrl(idle.file),
    idleClip: idle.animations.actions.idle, rotationY: 0, motions,
    interactions: Object.fromEntries(Object.entries(aliases).flatMap(([key, action]) => {
      const motion = motions.find((entry) => entry.action === action);
      return motion ? [[key, motion]] : [];
    })),
  };
}

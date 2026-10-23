import { validateFileLibraryManifest } from '@abby-assets/contracts';
import assetLock from '../../assets.lock.json';

const manifests = import.meta.glob('../avatar/shared/abby-streak-flames/**/manifest.json', { eager: true, import: 'default' });
const payloads = import.meta.glob('../avatar/shared/abby-streak-flames/**/objects/*.json', { eager: true, query: '?raw', import: 'default' });
// Emit the original runtime bytes as well as reading them. The ordinary
// importer and postbuild gate verify their exact SHA-256 and byte count.
const urls = import.meta.glob('../avatar/shared/abby-streak-flames/**/objects/*.json', { eager: true, query: '?url', import: 'default' });

export const STREAK_FLAME_FAMILY = 'abby-streak-flames';
export const STREAK_FLAME_PIN = Object.freeze({
  family_id: STREAK_FLAME_FAMILY,
  release_version: '1.0.0',
  manifest_sha256: 'e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64',
  directory: 'abby-streak-flames/1.0.0/e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64',
});
export const STREAK_FLAME_PAYLOAD = Object.freeze({
  sha256: 'dd285a472e0abcb80d0a87b70dcaf322602808f297bee73da76f4af952d3b435', bytes: 5253,
});
export const STREAK_FLAME_DIGESTS = Object.freeze({
  'dormant-ember': '37d6ba9fcf4111b558d334768c06cfb446539dfb3c58f5ebee00544ebd9ae270',
  'small-flame': 'bdbf5fe081a03f8e6af5b7dde3a1957c40e95d9456a9792976d76fe67bf0fa70',
  'strong-flame': '60c622a063e447f04106130656efd319eadfb1db179d38f3ab4d5dd9559c13fd',
  'maximum-blaze': '7a0536f486eb0875ac149ed851345a79d46427eb14d66552e1fdaea51d0e4894',
});

const exactKeys = (value, keys) => value !== null && typeof value === 'object' && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
const matchesPin = (pin) => pin && Object.entries(STREAK_FLAME_PIN).every(([key, value]) => pin[key] === value);

/** These SVGs are image documents, never injected HTML. The private importer
 * authenticates their bytes; this allowlist additionally rejects active or
 * externally loaded content if runtime metadata is malformed. */
function safeSvg(svg, stage) {
  if (typeof svg !== 'string' || svg.length > 16_384 || typeof DOMParser === 'undefined' || /<!/i.test(svg)) return false;
  const document = new DOMParser().parseFromString(svg, 'image/svg+xml');
  const root = document.documentElement;
  if (document.querySelector('parsererror') || root.localName !== 'svg' || root.namespaceURI !== 'http://www.w3.org/2000/svg'
    || root.getAttribute('viewBox') !== '0 0 24 24' || root.getAttribute('width') !== '24' || root.getAttribute('height') !== '24'
    || root.getAttribute('fill') !== 'none') return false;
  const allowed = {
    svg: ['xmlns', 'width', 'height', 'viewBox', 'fill'], title: [], defs: [],
    linearGradient: ['id', 'x1', 'y1', 'x2', 'y2', 'gradientUnits'], stop: ['offset', 'stop-color'],
    g: ['class', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin'],
    path: ['d', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin'],
  };
  const gradient = `fill-${stage}`;
  const ids = Array.from(root.querySelectorAll('[id]'));
  if (ids.length !== 1 || ids[0].localName !== 'linearGradient' || ids[0].id !== gradient) return false;
  return [root, ...root.querySelectorAll('*')].every((node) => Object.hasOwn(allowed, node.localName)
    && node.namespaceURI === root.namespaceURI && Array.from(node.attributes).every(({ name, value }) => {
      if (!allowed[node.localName].includes(name)) return false;
      if (['fill', 'stroke', 'stop-color'].includes(name)) return /^(?:none|#[a-fA-F0-9]{3,8})$/.test(value) || name === 'fill' && value === `url(#${gradient})`;
      if (name === 'class') return ['flame-body', 'flame-sparks'].includes(value);
      return !/[<>]/.test(value);
    }));
}

/** Accept only the exact release in the active lock. An evaluation pin or a
 * staged directory alone cannot activate unpublished artwork. */
export function stagedStreakFlameRelease(available = manifests, raw = payloads, lock = assetLock, fileUrls = urls) {
  const pins = Array.isArray(lock?.releases) ? lock.releases.filter((pin) => pin?.family_id === STREAK_FLAME_FAMILY) : [];
  if (pins?.length !== 1 || !matchesPin(pins[0])) return null;
  const pin = pins[0], prefix = `../avatar/shared/${pin.directory}/`;
  const manifest = available?.[`${prefix}manifest.json`];
  if (!manifest || manifest.family_id !== pin.family_id || manifest.release_version !== pin.release_version) return null;
  try { validateFileLibraryManifest(manifest); } catch { return null; }
  if (manifest.files.length !== 1 || manifest.entries.length !== 1) return null;
  const file = manifest.files[0], entry = manifest.entries[0];
  if (file.sha256 !== STREAK_FLAME_PAYLOAD.sha256 || file.bytes !== STREAK_FLAME_PAYLOAD.bytes || file.media_type !== 'application/json'
    || entry.id !== 'streak-flames' || entry.runtime_path !== 'streak/flames.runtime.json') return null;
  const content = raw?.[`${prefix}${file.path}`];
  if (typeof content !== 'string' || new TextEncoder().encode(content).byteLength !== file.bytes || !fileUrls?.[`${prefix}${file.path}`]) return null;
  let payload;
  try { payload = JSON.parse(content); } catch { return null; }
  if (!exactKeys(payload, ['schema_version', 'view_box', 'stages']) || payload.schema_version !== 1 || payload.view_box !== '0 0 24 24'
    || !exactKeys(payload.stages, Object.keys(STREAK_FLAME_DIGESTS))) return null;
  for (const [stage, digest] of Object.entries(STREAK_FLAME_DIGESTS)) {
    const row = payload.stages[stage];
    if (!exactKeys(row, ['filename', 'sha256', 'svg']) || row.filename !== `flame-${stage}.svg` || row.sha256 !== digest || !safeSvg(row.svg, stage)) return null;
  }
  return { pin, manifest, stages: payload.stages };
}

const installed = stagedStreakFlameRelease();

/** Keep each unchanged SVG in its own image document, so authored gradient
 * IDs cannot collide when several flames appear together. */
export function resolveStreakFlame(stage, staged = installed) {
  if (!Object.hasOwn(STREAK_FLAME_DIGESTS, stage) || !staged || !matchesPin(staged.pin)) return null;
  const row = staged.stages?.[stage];
  if (!row || row.sha256 !== STREAK_FLAME_DIGESTS[stage]) return null;
  return {
    url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(row.svg)}`,
    stage, filename: row.filename, sha256: row.sha256, width: 24, height: 24, viewBox: '0 0 24 24',
    family_id: staged.pin.family_id, release_version: staged.pin.release_version, manifest_sha256: staged.pin.manifest_sha256,
  };
}

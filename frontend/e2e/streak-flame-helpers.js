import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { isAbsolute, join, resolve } from 'node:path';

export const flameStages = ['dormant-ember', 'small-flame', 'strong-flame', 'maximum-blaze'];
const frontend = fileURLToPath(new URL('..', import.meta.url));
const checkout = resolve(frontend, '..');
const expectedManifest = 'e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64';
const expectedPayload = 'dd285a472e0abcb80d0a87b70dcaf322602808f297bee73da76f4af952d3b435';
const sha256 = (bytes) => createHash('sha256').update(bytes).digest('hex');

function installedFlames() {
  const lock = JSON.parse(readFileSync(join(frontend, 'assets.lock.json'), 'utf8'));
  const pins = lock.releases.filter((pin) => pin.family_id === 'abby-streak-flames');
  if (pins.length !== 1 || pins[0].release_version !== '1.0.0' || pins[0].manifest_sha256 !== expectedManifest
    || pins[0].directory !== `abby-streak-flames/1.0.0/${expectedManifest}`) return null;
  const directory = join(frontend, 'src/avatar/shared', pins[0].directory);
  const manifestPath = join(directory, 'manifest.json');
  if (!existsSync(manifestPath)) return null;
  const manifestBytes = readFileSync(manifestPath);
  if (sha256(manifestBytes) !== expectedManifest) return null;
  const manifest = JSON.parse(manifestBytes);
  const file = manifest.files?.[0];
  if (manifest.files.length !== 1 || file.sha256 !== expectedPayload || file.path !== `objects/${expectedPayload}.json`) return null;
  const payloadPath = join(directory, file.path);
  if (!existsSync(payloadPath)) return null;
  const bytes = readFileSync(payloadPath);
  if (bytes.byteLength !== file.bytes || sha256(bytes) !== expectedPayload) return null;
  const payload = JSON.parse(bytes);
  return { pin: pins[0], stages: Object.fromEntries(flameStages.map((stage) => [stage, {
    filename: payload.stages[stage].filename, sha256: payload.stages[stage].sha256,
  }])) };
}

export const privateFlames = installedFlames();
const evidence = process.env.ABBY_STREAK_FLAME_EVIDENCE_DIR;
if (evidence && (!isAbsolute(evidence) || resolve(evidence) === checkout || resolve(evidence).startsWith(`${checkout}/`))) {
  throw new Error('Flame evidence requires an absolute directory outside the checkout.');
}

export async function captureFlameEvidence(target, info, filename, options = {}) {
  if (!evidence) return;
  const directory = join(evidence, info.testId.replace(/[^a-zA-Z0-9-]/g, '-'));
  await mkdir(directory, { recursive: true });
  await target.screenshot({ ...options, path: join(directory, filename) });
}

export async function imageDocumentMetadata(image) {
  return image.evaluate(async (node) => {
    await node.decode();
    const source = decodeURIComponent(node.src.slice(node.src.indexOf(',') + 1));
    const document = new DOMParser().parseFromString(source, 'image/svg+xml');
    const root = document.documentElement;
    const ids = [...document.querySelectorAll('[id]')].map((element) => element.id);
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(source));
    return {
      viewBox: root.getAttribute('viewBox'), width: root.getAttribute('width'), height: root.getAttribute('height'),
      naturalWidth: node.naturalWidth, naturalHeight: node.naturalHeight,
      idCount: ids.length, uniqueIdCount: new Set(ids).size,
      activeElements: document.querySelectorAll('animate, animateTransform, style, script').length,
      sha256: [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join(''),
    };
  });
}

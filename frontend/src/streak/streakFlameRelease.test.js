import { describe, expect, it } from 'vitest';
import {
  STREAK_FLAME_FAMILY, STREAK_FLAME_PIN, STREAK_FLAME_PAYLOAD, STREAK_FLAME_DIGESTS,
  stagedStreakFlameRelease, resolveStreakFlame,
} from './streakFlameRelease';

// These tiny synthetic documents are unrelated to the private illustrations.
// The trusted importer supplies byte authenticity; these checks exercise the
// receiving schema, exact digest bindings and isolated SVG-image documents.
const syntheticSvg = (stage) => `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"><defs><linearGradient id="fill-${stage}"><stop stop-color="#000"/></linearGradient></defs><path d="M0 0h1" fill="url(#fill-${stage})"/></svg>`;

function fixture() {
  const file = { path: `objects/${STREAK_FLAME_PAYLOAD.sha256}.json`, ...STREAK_FLAME_PAYLOAD, media_type: 'application/json' };
  const manifest = { schema_version: 1, kind: 'file-library', family_id: STREAK_FLAME_FAMILY,
    release_version: STREAK_FLAME_PIN.release_version, label: 'Synthetic flame library', files: [file],
    entries: [{ id: 'streak-flames', runtime_path: 'streak/flames.runtime.json', file: file.path,
      ...STREAK_FLAME_PAYLOAD, media_type: 'application/json' }] };
  const payload = { schema_version: 1, view_box: '0 0 24 24', stages: Object.fromEntries(Object.entries(STREAK_FLAME_DIGESTS)
    .map(([stage, sha256]) => [stage, { filename: `flame-${stage}.svg`, sha256, svg: syntheticSvg(stage) }])) };
  const prefix = `../avatar/shared/${STREAK_FLAME_PIN.directory}/`;
  const available = { [`${prefix}manifest.json`]: manifest };
  const urls = { [`${prefix}${file.path}`]: '/synthetic/flames.json' };
  const lock = { releases: [STREAK_FLAME_PIN] };
  const raw = () => {
    const value = JSON.stringify(payload);
    return { [`${prefix}${file.path}`]: value.padEnd(STREAK_FLAME_PAYLOAD.bytes, ' ') };
  };
  const staged = () => stagedStreakFlameRelease(available, raw(), lock, urls);
  return { manifest, file, payload, prefix, available, urls, lock, raw, staged };
}

describe('Private streak flame release', () => {
  it('preserves all four complete SVG documents and release identities in isolated image URLs', () => {
    const f = fixture(), staged = f.staged();
    expect(staged).not.toBeNull();
    for (const stage of Object.keys(STREAK_FLAME_DIGESTS)) {
      const result = resolveStreakFlame(stage, staged);
      expect(result).toMatchObject({ stage, width: 24, height: 24, viewBox: '0 0 24 24',
        family_id: STREAK_FLAME_FAMILY, release_version: STREAK_FLAME_PIN.release_version,
        manifest_sha256: STREAK_FLAME_PIN.manifest_sha256, sha256: STREAK_FLAME_DIGESTS[stage] });
      expect(result.url.startsWith('data:image/svg+xml;charset=utf-8,')).toBe(true);
      expect(decodeURIComponent(result.url.split(',')[1])).toBe(f.payload.stages[stage].svg);
      expect(resolveStreakFlame(stage, staged).url).toBe(result.url);
    }
  });

  it('does not activate an evaluation candidate, absent install or unknown stage', () => {
    const f = fixture();
    expect(stagedStreakFlameRelease(f.available, f.raw(), { releases: [] }, f.urls)).toBeNull();
    expect(stagedStreakFlameRelease({}, f.raw(), f.lock, f.urls)).toBeNull();
    expect(stagedStreakFlameRelease(f.available, {}, f.lock, f.urls)).toBeNull();
    expect(stagedStreakFlameRelease(f.available, f.raw(), f.lock, {})).toBeNull();
    for (const stage of [null, 'unknown', 'constructor', 'blazing', '']) expect(resolveStreakFlame(stage, f.staged())).toBeNull();
    for (const stage of Object.keys(STREAK_FLAME_DIGESTS)) expect(resolveStreakFlame(stage, null)).toBeNull();
    // The active lock intentionally contains no unpublished flame release.
    expect(resolveStreakFlame('dormant-ember')).toBeNull();
  });

  it('requires one exact active pin and a matching manifest family and version', () => {
    const f = fixture();
    for (const lock of [null, {}, { releases: {} }, { releases: [STREAK_FLAME_PIN, STREAK_FLAME_PIN] }]) {
      expect(stagedStreakFlameRelease(f.available, f.raw(), lock, f.urls)).toBeNull();
    }
    for (const change of [{ family_id: 'other-family' }, { release_version: '1.0.1' }, { manifest_sha256: 'f'.repeat(64) }, { directory: 'other/1.0.0/pin' }]) {
      expect(stagedStreakFlameRelease(f.available, f.raw(), { releases: [{ ...STREAK_FLAME_PIN, ...change }] }, f.urls)).toBeNull();
    }
    for (const change of [{ family_id: 'other-family' }, { release_version: '1.0.1' }, { kind: 'asset-pack' }]) {
      expect(stagedStreakFlameRelease({ [`${f.prefix}manifest.json`]: { ...f.manifest, ...change } }, f.raw(), f.lock, f.urls)).toBeNull();
    }
  });

  it('rejects payload metadata drift, additional files, missing entries and wrong runtime mappings', () => {
    for (const mutate of [
      (f) => { f.manifest.entries = []; },
      (f) => { f.manifest.files.push({ ...f.file }); },
      (f) => { f.file.bytes--; },
      (f) => { f.file.media_type = 'image/png'; },
      (f) => { f.manifest.entries[0].runtime_path = 'another.json'; },
      (f) => { f.manifest.entries[0].id = 'other'; },
      (f) => { f.manifest.entries[0].sha256 = 'f'.repeat(64); },
    ]) { const f = fixture(); mutate(f); expect(f.staged()).toBeNull(); }
    const f = fixture(), raw = f.raw(), path = Object.keys(raw)[0];
    expect(stagedStreakFlameRelease(f.available, { [path]: raw[path].slice(1) }, f.lock, f.urls)).toBeNull();
    expect(stagedStreakFlameRelease(f.available, { [path]: '!'.repeat(STREAK_FLAME_PAYLOAD.bytes) }, f.lock, f.urls)).toBeNull();
  });

  it('rejects incomplete stages, digest substitution, renamed files and unknown schema fields', () => {
    for (const mutate of [
      (f) => { f.payload.schema_version = 2; },
      (f) => { f.payload.view_box = '0 0 32 32'; },
      (f) => { delete f.payload.stages['maximum-blaze']; },
      (f) => { f.payload.stages.extra = f.payload.stages['small-flame']; },
      (f) => { f.payload.stages['small-flame'].sha256 = STREAK_FLAME_DIGESTS['strong-flame']; },
      (f) => { f.payload.stages['small-flame'].filename = 'substituted.svg'; },
      (f) => { f.payload.stages['small-flame'].extra = 'unsupported'; },
      (f) => { f.payload.extra = 'unsupported'; },
    ]) { const f = fixture(); mutate(f); expect(f.staged()).toBeNull(); }
  });

  it('rejects executable, external, malformed or differently cropped SVG content', () => {
    for (const transform of [
      (svg) => svg.replace('<defs>', '<script>alert(1)</script><defs>'),
      (svg) => svg.replace('<defs>', '<image href="https://example.invalid/extra.svg"/><defs>'),
      (svg) => svg.replace('width="24"', 'width="24" onload="alert(1)"'),
      (svg) => svg.replace('fill="none"', 'fill="url(https://example.invalid/paint)"'),
      (svg) => svg.replace('0 0 24 24', '0 0 20 20'),
      (svg) => svg.replace('</svg>', ''),
      (svg) => svg.replace('<defs>', '<defs id="duplicate">'),
      (svg) => `<!DOCTYPE svg>${svg}`,
      (svg) => svg.replace('fill-small-flame', 'unbound-gradient'),
    ]) { const f = fixture(); f.payload.stages['small-flame'].svg = transform(f.payload.stages['small-flame'].svg); expect(f.staged()).toBeNull(); }
  });
});

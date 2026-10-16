import { describe, expect, it } from 'vitest';
import { birdMotions, birdStage, resolveSharedBirdAppearance, stagedBirdRelease } from './sharedBirdRelease';
import { stagedBirdFixture, syntheticBird } from '../test/birdReleaseFixture';

describe('Pinned shared bird release', () => {
  it('exposes all 31 native motions and selects only server-confirmed stages', () => {
    const staged = stagedBirdFixture();
    expect(['chick', 'fledgling', 'bird'].flatMap((stage) => birdMotions(staged.release, stage, staged.resolveUrl))).toHaveLength(31);
    expect(resolveSharedBirdAppearance(syntheticBird, 'pet', staged).key).toBe('chick');
    expect(resolveSharedBirdAppearance({ ...syntheticBird, evolution_stage: 'fledgling' }, 'pet', staged).key).toBe('fledgling');
    expect(resolveSharedBirdAppearance({ ...syntheticBird, evolved_to_mount: true }, 'pet', staged).key).toBe('bird');
    expect(resolveSharedBirdAppearance(syntheticBird, 'mount', staged).key).toBe('bird');
    expect(resolveSharedBirdAppearance({ ...syntheticBird, evolution_stage: 'bird' }, 'pet', staged)).toBeNull();
    expect(resolveSharedBirdAppearance({ ...syntheticBird, potion: { slug: 'fire' } }, 'pet', staged)).toBeNull();
    expect(birdStage({ ...syntheticBird, species: { slug: 'fox', sprite_key: 'cute-chick' } })).toBeNull();
    expect(birdStage({ ...syntheticBird, id: null })).toBeNull();
  });

  it('requires the exact pinned family, version, manifest URL and complete payload inventory', () => {
    const { release } = stagedBirdFixture();
    const pin = { family_id: release.family_id, release_version: release.release_version, directory: 'bird/1.0.0/pin', manifest_sha256: 'a'.repeat(64) };
    const prefix = `../avatar/shared/${pin.directory}/`;
    const available = { [`${prefix}manifest.json`]: release };
    const urls = Object.fromEntries(release.files.map((file) => [`${prefix}${file.path}`, `/test/${file.path}`]));
    const indexes = { [`${prefix}manifest.json`]: '/test/manifest.json' };
    expect(stagedBirdRelease(available, urls, { releases: [pin] }, indexes).manifestSha256).toBe(pin.manifest_sha256);
    expect(stagedBirdRelease(available, urls, { releases: [] }, indexes)).toBeNull();
    expect(stagedBirdRelease(available, urls, { releases: [{ ...pin, release_version: '2.0.0' }] }, indexes)).toBeNull();
    expect(stagedBirdRelease(available, urls, { releases: [pin] }, {})).toBeNull();
    delete urls[Object.keys(urls)[0]];
    expect(stagedBirdRelease(available, urls, { releases: [pin] }, indexes)).toBeNull();
    expect(stagedBirdRelease({ [`${prefix}manifest.json`]: { ...release, kind: 'avatar-family' } }, {}, { releases: [pin] }, indexes)).toBeNull();
  });
});

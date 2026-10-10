import { describe, expect, it } from 'vitest';
import { resolveCompanionPresentation } from './companionPresentation';

const publicPresentation = {
  schema_version: 1,
  companion: {
    id: 'starter-friend', label: 'Your dragon', art_key: 'dragon', temporary: true,
    portrait: 'dragon-idle.png', happy_portrait: 'dragon-happy.png', blink_portrait: 'dragon-blink.png',
  },
};
const publicArt = (name) => ({
  'dragon-idle.png': '/assets/placeholder-idle.png',
  'dragon-happy.png': '/assets/placeholder-happy.png',
  'dragon-blink.png': '/assets/placeholder-blink.png',
})[name];
const licensedPresentation = {
  schema_version: 1,
  companion: {
    id: 'starter-friend', label: 'Your chick', art_key: 'chick', temporary: false,
    portrait: 'chick.png', happy_portrait: 'chick.png', blink_portrait: 'chick.png',
  },
};
const licensedArt = (name) => name === 'chick.png' ? '/assets/chick-a1b2.png' : undefined;
const resolve = (manifest, art = licensedArt) => resolveCompanionPresentation(publicPresentation, publicArt, manifest, art);

describe('Meadow companion presentation', () => {
  it('keeps the public checkout usable without a licensed staging folder', () => {
    expect(resolve()).toEqual({
      id: 'starter-friend', name: 'Your dragon', artKey: 'dragon', temporary: true,
      portrait: '/assets/placeholder-idle.png', happyPortrait: '/assets/placeholder-happy.png',
      blinkPortrait: '/assets/placeholder-blink.png',
    });
  });

  it('uses the configured companion and its bundled portrait without changing identity', () => {
    expect(resolve(licensedPresentation)).toEqual({
      id: 'starter-friend', name: 'Your chick', artKey: 'chick', temporary: false,
      portrait: '/assets/chick-a1b2.png', happyPortrait: '/assets/chick-a1b2.png',
      blinkPortrait: '/assets/chick-a1b2.png',
    });
  });

  it('falls back completely if the configured portrait was not staged', () => {
    expect(resolve(licensedPresentation, () => undefined)).toEqual(resolve());
  });

  it('keeps the resting portrait when a pack has no separate expression artwork', () => {
    const manifest = { ...licensedPresentation, companion: { ...licensedPresentation.companion, happy_portrait: 'absent.png', blink_portrait: undefined } };
    const companion = resolve(manifest);
    expect(companion.happyPortrait).toBe('/assets/chick-a1b2.png');
    expect(companion.blinkPortrait).toBe('/assets/chick-a1b2.png');
  });

  it.each([
    { ...licensedPresentation, schema_version: 2 },
    { ...licensedPresentation, companion: { ...licensedPresentation.companion, id: 'another-friend' } },
    { ...licensedPresentation, companion: { ...licensedPresentation.companion, label: ' ' } },
    { schema_version: 1 },
  ])('ignores an incomplete or incompatible local presentation (%j)', (manifest) => {
    expect(resolve(manifest)).toEqual(resolve());
  });
});

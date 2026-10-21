// Code-native ornaments for saved catalog frames. Names support older compact
// profile responses, which did not include the catalog slug.
const FRAMES = [
  ['bronze', 'Bronze Frame', 'gold-leaf'],
  ['silver', 'Silver Frame', 'ink-secondary'],
  ['gold', 'Gold Frame', 'gold-leaf'],
  ['cosmic', 'Cosmic Frame', 'royal'],
  ['barbute', 'Barbute Helm Frame', 'ink-secondary'],
  ['robin-hood', "Ranger's Cap Frame", 'moss'],
  ['cross-helm', 'Paladin Helm Frame', 'gold-leaf'],
  ['scholar', 'Scholar Frame', 'gold-leaf'],
  ['laurel', 'Laurel Wreath Frame', 'moss'],
  ['rune-circle', 'Rune Circle Frame', 'sheikah-teal-deep'],
  ['steampunk', 'Steampunk Gear Frame', 'gold-leaf'],
  ['pixel', 'Pixel Pixel Frame', 'moss'],
  ['high-school-trophy', 'High School Trophy Frame', 'gold-leaf'],
  ['moonlit', 'Moonlit Frame', 'sheikah-teal-deep'],
  ['confetti', 'Confetti Frame', 'rose'],
  ['seashell', 'Seashell Frame', 'rose'],
  ['chronicle', 'Chronicle Frame', 'gold-leaf'],
  ['far-horizons', 'Far Horizons Frame', 'sheikah-teal-deep'],
];

export function portraitFrame(frame) {
  if (!frame) return { family: 'plain' };
  const known = FRAMES.find(([family, name]) => frame.slug
    ? frame.slug === `frame-${family}` || frame.slug.endsWith(`-frame-${family}`)
    : frame.name === name);
  return known
    ? { family: known[0], color: `var(--color-${known[2]})` }
    : { family: 'custom', color: frame.metadata?.border_color || 'var(--color-sheikah-teal-deep)' };
}

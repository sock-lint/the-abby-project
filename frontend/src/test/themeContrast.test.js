import { describe, it, expect } from 'vitest';
import { themes } from '../themes';
import { contrastRatio } from '../utils/contrast';

// WCAG 2.1 AA minimums:
//   - 4.5:1 for normal body text.
//   - 3.0:1 for large text (≥18pt / 14pt bold). Use this for chip/pill
//     labels where the rendered glyph is effectively large.
const AA_NORMAL = 4.5;
const AA_LARGE = 3.0;

// Surfaces every cover must remain readable on. `page` is the base body
// background; `pageAged` is the default ParchmentCard fill; `pageGlow`
// is the "bright" ParchmentCard spotlight (e.g. HeroPrimaryCard).
const SURFACES = ['page', 'pageAged', 'pageGlow'];

// Ink hierarchy: all three must pass normal-text AA on both surfaces.
// These render as paragraph/caption text, not chips.
const INK_KEYS = ['ink', 'inkSecondary', 'inkWhisper'];

// Accent tones that appear as chip/pill text (HeaderStatusPips, RuneBadge,
// rarity labels, etc.). Rendered in short bold runs, so large-text AA is
// the right bar here — and matches how the app actually uses them.
const TONE_KEYS = ['goldLeaf', 'moss', 'mossDeep', 'emberDeep', 'royal', 'rose'];

// The 2 Sheikah accents and the ember highlight are also rendered as chip
// text or button labels — hold them to large-text AA too.
const ACCENT_KEYS = ['accent', 'accentBright', 'ember'];

describe('theme contrast (WCAG AA)', () => {
  for (const [themeKey, theme] of Object.entries(themes)) {
    describe(`${themeKey} (${theme.name})`, () => {
      for (const surface of SURFACES) {
        const bg = theme[surface];

        for (const inkKey of INK_KEYS) {
          it(`${inkKey} on ${surface} ≥ ${AA_NORMAL}:1`, () => {
            const ratio = contrastRatio(theme[inkKey], bg);
            expect(
              ratio,
              `${theme[inkKey]} on ${bg} = ${ratio.toFixed(2)}:1`,
            ).toBeGreaterThanOrEqual(AA_NORMAL);
          });
        }

        for (const toneKey of TONE_KEYS) {
          it(`tones.${toneKey} on ${surface} ≥ ${AA_LARGE}:1`, () => {
            const tone = theme.tones?.[toneKey];
            const ratio = contrastRatio(tone, bg);
            expect(
              ratio,
              `${tone} on ${bg} = ${ratio.toFixed(2)}:1`,
            ).toBeGreaterThanOrEqual(AA_LARGE);
          });
        }

        for (const accentKey of ACCENT_KEYS) {
          it(`${accentKey} on ${surface} ≥ ${AA_LARGE}:1`, () => {
            const ratio = contrastRatio(theme[accentKey], bg);
            expect(
              ratio,
              `${theme[accentKey]} on ${bg} = ${ratio.toFixed(2)}:1`,
            ).toBeGreaterThanOrEqual(AA_LARGE);
          });
        }
      }
    });
  }
});

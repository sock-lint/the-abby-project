import { describe, it, expect } from 'vitest';
import { themes } from '../themes';
import { contrastRatio, hexToRgb } from '../utils/contrast';
import { STATUS_COLORS, RARITY_PILL_COLORS } from '../constants/colors';
import { buttonDanger } from '../constants/styles';

// Every body/caption/chip label must meet normal-text AA. The app uses small
// labels throughout, so a large-text-only threshold would miss regressions.
const AA_NORMAL = 4.5;

// Surfaces every cover must remain readable on. `page` is the base body
// background; `pageAged` is the default ParchmentCard fill; `pageGlow`
// is the "bright" ParchmentCard spotlight (e.g. HeroPrimaryCard).
const SURFACES = ['page', 'pageAged', 'pageGlow'];

// Ink hierarchy: all three must pass normal-text AA on each surface.
// These render as paragraph/caption text, not chips.
const INK_KEYS = ['ink', 'inkSecondary', 'inkWhisper'];

// Accent tones that appear as chip/pill text (HeaderStatusPips, RuneBadge,
// rarity labels, etc.). These small labels need normal-text AA too.
const TONE_KEYS = ['goldLeaf', 'moss', 'mossDeep', 'emberDeep', 'royal', 'rose'];

// Accent and alert tokens also render as chip text and button labels.
const ACCENT_KEYS = ['accent', 'accentBright', 'ember'];

// Navigation and status chips paint translucent tones over the page. Check
// the resulting surface rather than assuming base-page contrast carries over.
function tintedSurface(tone, base, opacity) {
  const fg = hexToRgb(tone);
  const bg = hexToRgb(base);
  return '#' + ['r', 'g', 'b'].map((channel) =>
    Math.round(fg[channel] * opacity + bg[channel] * (1 - opacity))
      .toString(16).padStart(2, '0'),
  ).join('');
}

describe('theme contrast (WCAG AA)', () => {
  for (const [themeKey, theme] of Object.entries(themes)) {
    describe(`${themeKey} (${theme.name})`, () => {
      it('keeps the small notification count readable on its ember badge', () => {
        expect(contrastRatio(theme.page, theme.tones.emberDeep)).toBeGreaterThanOrEqual(AA_NORMAL);
      });
      it('keeps nested-card supporting copy readable over every owning surface', () => {
        for (const surface of SURFACES) {
          const background = tintedSurface(theme.pageShadow, theme[surface], 0.8);
          for (const inkKey of INK_KEYS) {
            expect(contrastRatio(theme[inkKey], background), `${inkKey} on deep card over ${surface}`).toBeGreaterThanOrEqual(AA_NORMAL);
          }
        }
      });
      it('keeps shared status, rarity and danger labels readable on their tinted surfaces', () => {
        const tokens = {
          'ink-primary': theme.ink, 'ink-secondary': theme.inkSecondary,
          'ink-whisper': theme.inkWhisper, 'ink-page-shadow': theme.pageShadow,
          'sheikah-teal': theme.accentBright, 'sheikah-teal-deep': theme.accent,
          ember: theme.ember, 'ember-deep': theme.tones.emberDeep,
          moss: theme.tones.moss, royal: theme.tones.royal,
          'gold-leaf': theme.tones.goldLeaf,
        };
        const labels = { ...STATUS_COLORS, ...RARITY_PILL_COLORS, danger: buttonDanger };
        for (const [name, classes] of Object.entries(labels)) {
          const foreground = tokens[classes.match(/\btext-([a-z-]+)/)[1]];
          for (const match of classes.matchAll(/(?:^|\s)(?:hover:)?bg-([a-z-]+)(?:\/(\d+))?/g)) {
            for (const surface of SURFACES) {
              const background = tintedSurface(tokens[match[1]], theme[surface], Number(match[2] || 100) / 100);
              expect(contrastRatio(foreground, background), `${name} label over ${surface}`).toBeGreaterThanOrEqual(AA_NORMAL);
            }
          }
        }
      });
      for (const surface of ['page', 'pageAged']) {
        for (const tone of [theme.accentBright, theme.tones.goldLeaf, theme.tones.emberDeep]) {
          for (const opacity of [0.1, 0.15]) {
            it(`active/status label on ${tone} at ${opacity} over ${surface} ≥ ${AA_NORMAL}:1`, () => {
              const bg = tintedSurface(tone, theme[surface], opacity);
              expect(contrastRatio(theme.ink, bg)).toBeGreaterThanOrEqual(AA_NORMAL);
            });
          }
        }
      }
      for (const surface of SURFACES) {
        const bg = theme[surface];

        it(`chapter marker on moss/15 over ${surface} ≥ ${AA_NORMAL}:1`, () => {
          const markerSurface = tintedSurface(theme.tones.moss, bg, 0.15);
          expect(contrastRatio(theme.tones.mossDeep, markerSurface)).toBeGreaterThanOrEqual(AA_NORMAL);
        });

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
          it(`tones.${toneKey} on ${surface} ≥ ${AA_NORMAL}:1`, () => {
            const tone = theme.tones?.[toneKey];
            const ratio = contrastRatio(tone, bg);
            expect(
              ratio,
              `${tone} on ${bg} = ${ratio.toFixed(2)}:1`,
            ).toBeGreaterThanOrEqual(AA_NORMAL);
          });
        }

        for (const accentKey of ACCENT_KEYS) {
          it(`${accentKey} on ${surface} ≥ ${AA_NORMAL}:1`, () => {
            const ratio = contrastRatio(theme[accentKey], bg);
            expect(
              ratio,
              `${theme[accentKey]} on ${bg} = ${ratio.toFixed(2)}:1`,
            ).toBeGreaterThanOrEqual(AA_NORMAL);
          });
        }
      }
    });
  }
});

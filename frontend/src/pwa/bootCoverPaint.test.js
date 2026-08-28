import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { LEGACY_THEME_ALIASES, themes } from '../themes.js';
import { STORAGE_KEYS } from '../constants/storage.js';

// index.html carries a tiny inline script that paints the saved journal cover
// before the deferred app bundle boots — without it a kid on the dark Night
// Vigil cover gets a full-screen cream flash on every cold launch of the
// installed PWA. It can't import themes.js (it has to run before any module
// does), so it inlines its own copy of the six page colors. These tests are
// the gate that keeps that copy honest.
// `import.meta.url` resolves to Vitest's transform URL, not a file path, so
// read from the project root instead (vitest's cwd/root is `frontend/`).
const html = readFileSync(resolve(process.cwd(), 'index.html'), 'utf8');

function parseInlineMap(name) {
  const block = html.match(new RegExp(`var ${name} = \\{([\\s\\S]*?)\\};`));
  expect(block, `index.html no longer declares ${name}`).toBeTruthy();
  const entries = [...block[1].matchAll(/(\w+):\s*'([^']+)'/g)];
  return Object.fromEntries(entries.map(([, key, value]) => [key, value]));
}

describe('index.html pre-hydration cover paint', () => {
  it('inlines the exact page color of every cover in themes.js', () => {
    const expected = Object.fromEntries(
      Object.entries(themes).map(([key, theme]) => [key, theme.page]),
    );
    expect(parseInlineMap('COVER_PAGE')).toEqual(expected);
  });

  it('inlines the same legacy cover aliases themes.js maps forward', () => {
    expect(parseInlineMap('LEGACY_ALIASES')).toEqual(LEGACY_THEME_ALIASES);
  });

  it('reads the cover from the cached-user snapshot AuthProvider writes', () => {
    expect(html).toContain(`'${STORAGE_KEYS.CACHED_USER}'`);
  });

  it('paints only the page background token, leaving applyTheme() in charge', () => {
    expect(html).toContain("setProperty('--color-ink-page', page)");
  });
});

describe('index.html installed-app chrome', () => {
  // Five of the six covers are light parchment, and this value is baked in at
  // install time — black-translucent renders the iOS clock/battery in white,
  // i.e. invisible on cream, for every kid except the one on Night Vigil.
  it('uses a status bar style that stays legible on the light covers', () => {
    expect(html).toMatch(
      /<meta name="apple-mobile-web-app-status-bar-style" content="default" \/>/,
    );
  });
});

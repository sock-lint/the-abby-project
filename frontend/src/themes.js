// Journal covers. Each theme defines the parchment core + Sheikah accent +
// a `tones` block of accent colors that are tuned to pass WCAG AA (≥4.5:1)
// against the cover's own page + pageAged surfaces. This replaces the
// previous model where tones like gold-leaf, ember-deep, moss, royal, and
// rose were global constants in index.css — those failed contrast on most
// covers (light gold on cream, dark ember on the dark vigil page, etc.).
// See frontend/src/test/themeContrast.test.js for the regression gate.

// Legacy-named aliases: each theme also exposes `bg`, `primary`, `highlight`,
// and `glow` so any call-site still using the old theme shape (e.g. the
// Settings swatch preview) keeps working. New code should prefer the
// `page / accent / accentBright` names.
const legacyAliases = (t) => ({
  ...t,
  bg: t.page,
  cardBg: t.pageAged,
  primary: t.accent,
  highlight: t.accentBright,
  glow: t.accentGlow,
});

const hyrule = {
  name: 'Hyrule Day',
  icon: '📖',
  page: '#f4ecd8',
  pageAged: '#e8dcc0',
  pageShadow: '#d4c7a6',
  pageGlow: '#fff8e0',
  ink: '#2d1f15',
  inkSecondary: '#6b5639',
  inkWhisper: '#755a38',
  accent: '#157064',
  accentBright: '#1d8a80',
  accentGlow: '#fff8e0',
  ember: '#a04a28',
  tones: {
    goldLeaf: '#856418',
    moss: '#456a3a',
    mossDeep: '#385829',
    emberDeep: '#8f3e1d',
    royal: '#5449a3',
    rose: '#a54865',
  },
};

const vigil = {
  name: 'Night Vigil',
  icon: '🕯️',
  page: '#2a1f15',
  pageAged: '#3a2c1f',
  pageShadow: '#1e1610',
  pageGlow: '#4a3d2e',
  ink: '#f4e8cc',
  inkSecondary: '#d4bf95',
  inkWhisper: '#c2ac88',
  accent: '#7fe3f0',
  accentBright: '#a8ecf5',
  accentGlow: '#4dd0e1',
  ember: '#f59e5a',
  tones: {
    goldLeaf: '#e8c770',
    moss: '#a8c48a',
    mossDeep: '#8fb070',
    emberDeep: '#f5b785',
    royal: '#b0a4f0',
    rose: '#eaa8ba',
  },
};

const sunlit = {
  name: 'Sunlit Field',
  icon: '☀️',
  page: '#f7ecc9',
  pageAged: '#ebd9a8',
  pageShadow: '#d4bb80',
  pageGlow: '#fff3c4',
  ink: '#3d2818',
  inkSecondary: '#7a5a32',
  inkWhisper: '#725428',
  accent: '#8a420f',
  accentBright: '#a85014',
  accentGlow: '#fde4b3',
  ember: '#a04a28',
  tones: {
    goldLeaf: '#8a6310',
    moss: '#4e7536',
    mossDeep: '#3c5a28',
    emberDeep: '#8f3e1d',
    royal: '#5a4e9c',
    rose: '#a84860',
  },
};

const snowquill = {
  name: 'Snowquill Tome',
  icon: '❄️',
  page: '#e8eef5',
  pageAged: '#d6dfeb',
  pageShadow: '#b8c5d6',
  pageGlow: '#f4f9ff',
  ink: '#1a2638',
  inkSecondary: '#3e5170',
  inkWhisper: '#49597a',
  accent: '#284c82',
  accentBright: '#2e5a99',
  accentGlow: '#c8dbed',
  ember: '#8a5a2a',
  tones: {
    goldLeaf: '#7a5a14',
    moss: '#3c6a2d',
    mossDeep: '#2e5220',
    emberDeep: '#7a3e18',
    royal: '#4a3e98',
    rose: '#9a3a58',
  },
};

const verdant = {
  name: 'Verdant Pages',
  icon: '🌿',
  page: '#eff0d7',
  pageAged: '#dcdcb0',
  pageShadow: '#b8ba86',
  pageGlow: '#f5f6e0',
  ink: '#1e2a15',
  inkSecondary: '#3f5030',
  inkWhisper: '#506036',
  accent: '#3d6126',
  accentBright: '#4d7532',
  accentGlow: '#d8e6b8',
  ember: '#9a5a2a',
  tones: {
    goldLeaf: '#7a5a14',
    moss: '#3f6630',
    mossDeep: '#2e4f22',
    emberDeep: '#8a3e18',
    royal: '#4d4098',
    rose: '#a03c5a',
  },
};

const harvest = {
  name: 'Harvest Folio',
  icon: '🍂',
  page: '#f0dcc0',
  pageAged: '#dcc29a',
  pageShadow: '#b89968',
  pageGlow: '#f7e8cc',
  ink: '#2e1a0d',
  inkSecondary: '#5e3a1f',
  inkWhisper: '#664423',
  accent: '#823618',
  accentBright: '#9e4520',
  accentGlow: '#f2c896',
  ember: '#823618',
  tones: {
    goldLeaf: '#6f4a10',
    moss: '#3f5f2a',
    mossDeep: '#314a20',
    emberDeep: '#7a2f18',
    royal: '#473a8f',
    rose: '#98334f',
  },
};

export const themes = {
  hyrule: legacyAliases(hyrule),
  vigil: legacyAliases(vigil),
  sunlit: legacyAliases(sunlit),
  snowquill: legacyAliases(snowquill),
  verdant: legacyAliases(verdant),
  harvest: legacyAliases(harvest),
};

// Legacy theme keys used by existing user records map forward onto the
// new covers so no migration is needed on the backend.
export const LEGACY_THEME_ALIASES = {
  summer: 'sunlit',
  winter: 'snowquill',
  spring: 'verdant',
  autumn: 'harvest',
};

export function applyTheme(themeName) {
  const resolved = LEGACY_THEME_ALIASES[themeName] || themeName;
  const theme = themes[resolved] || themes.hyrule;
  const root = document.documentElement;

  // Journal tokens
  root.style.setProperty('--color-ink-page', theme.page);
  root.style.setProperty('--color-ink-page-aged', theme.pageAged);
  root.style.setProperty('--color-ink-page-shadow', theme.pageShadow);
  root.style.setProperty('--color-ink-page-rune-glow', theme.pageGlow);
  root.style.setProperty('--color-ink-primary', theme.ink);
  root.style.setProperty('--color-ink-secondary', theme.inkSecondary);
  root.style.setProperty('--color-ink-whisper', theme.inkWhisper);
  root.style.setProperty('--color-sheikah-teal', theme.accentBright);
  root.style.setProperty('--color-sheikah-teal-deep', theme.accent);
  root.style.setProperty('--color-ember', theme.ember);

  // Per-theme accent tones — these used to be global constants in
  // index.css and failed contrast on most covers. Now tuned per theme.
  const t = theme.tones || {};
  if (t.goldLeaf) root.style.setProperty('--color-gold-leaf', t.goldLeaf);
  if (t.moss) root.style.setProperty('--color-moss', t.moss);
  if (t.mossDeep) root.style.setProperty('--color-moss-deep', t.mossDeep);
  if (t.emberDeep) root.style.setProperty('--color-ember-deep', t.emberDeep);
  if (t.royal) root.style.setProperty('--color-royal', t.royal);
  if (t.rose) root.style.setProperty('--color-rose', t.rose);

  // Legacy aliases — keep forge + amber pointing at the new palette so
  // un-migrated components still look right.
  root.style.setProperty('--color-forge-bg', theme.page);
  root.style.setProperty('--color-forge-card', theme.pageAged);
  root.style.setProperty('--color-forge-border', theme.pageShadow);
  root.style.setProperty('--color-forge-muted', theme.pageShadow);
  root.style.setProperty('--color-forge-text', theme.ink);
  root.style.setProperty('--color-forge-text-dim', theme.inkSecondary);
  root.style.setProperty('--color-amber-primary', theme.accent);
  root.style.setProperty('--color-amber-highlight', theme.accentBright);
  root.style.setProperty('--color-amber-glow', theme.accentGlow);

  // Audit L4: deliberately NOT setting ``document.body.style.background``.
  // ``index.css`` already has ``body { background-color: var(--color-ink-page) }``
  // and we update ``--color-ink-page`` above — so the body picks up the
  // new theme automatically. Inline-styling body fights Tailwind class
  // specificity (anything ``bg-ink-page`` on body would be silently
  // overridden) and made the live theme-preview hover restore-path
  // brittle.
}

// Journal covers. Each theme defines the parchment core + Sheikah accent.
// The legacy `--color-forge-*` + `--color-amber-*` variables are kept as
// aliases so un-migrated pages stay coherent during the Hyrule Field Notes
// rollout.

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
  inkWhisper: '#a08a6c',
  accent: '#26a69a',
  accentBright: '#4dd0e1',
  accentGlow: '#fff8e0',
  ember: '#d97548',
};

const vigil = {
  name: 'Night Vigil',
  icon: '🕯️',
  page: '#2a1f15',
  pageAged: '#3a2c1f',
  pageShadow: '#1e1610',
  pageGlow: '#4dd0e1',
  ink: '#e8dcc0',
  inkSecondary: '#a08a6c',
  inkWhisper: '#6b5639',
  accent: '#4dd0e1',
  accentBright: '#7fe3f0',
  accentGlow: '#4dd0e1',
  ember: '#f59e5a',
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
  inkWhisper: '#b59866',
  accent: '#c67a3e',
  accentBright: '#f2a857',
  accentGlow: '#fde4b3',
  ember: '#d97548',
};

const snowquill = {
  name: 'Snowquill Tome',
  icon: '❄️',
  page: '#e8eef5',
  pageAged: '#d6dfeb',
  pageShadow: '#b8c5d6',
  pageGlow: '#f4f9ff',
  ink: '#1a2638',
  inkSecondary: '#4a5d7a',
  inkWhisper: '#8499b3',
  accent: '#3e73b8',
  accentBright: '#6ba3d9',
  accentGlow: '#c8dbed',
  ember: '#a88660',
};

const verdant = {
  name: 'Verdant Pages',
  icon: '🌿',
  page: '#eff0d7',
  pageAged: '#dcdcb0',
  pageShadow: '#b8ba86',
  pageGlow: '#f5f6e0',
  ink: '#1e2a15',
  inkSecondary: '#4a5e35',
  inkWhisper: '#849268',
  accent: '#5b8a3f',
  accentBright: '#8fb56b',
  accentGlow: '#d8e6b8',
  ember: '#c47842',
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
  inkWhisper: '#9a7550',
  accent: '#a04a28',
  accentBright: '#d9693e',
  accentGlow: '#f2c896',
  ember: '#d97548',
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

  document.body.style.background = theme.page;
}

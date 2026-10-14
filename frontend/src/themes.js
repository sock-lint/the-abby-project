import presentation from './storybook/presentation.json';

// Keep persisted cover keys and cosmetic ownership intact. Every cover now
// belongs to Meadow's storybook family; the default uses its shared palette.
const { palette } = presentation;
const lightTones = {
  goldLeaf: '#866329', moss: '#486B55', mossDeep: '#3C5C48',
  emberDeep: '#A24C41', royal: '#685093', rose: '#A24F6F',
};

function cover(overrides) {
  const theme = {
    page: palette.paper,
    pageAged: '#FBF6FF',
    pageShadow: palette.lavender,
    pageGlow: palette.paper,
    ink: palette.ink,
    // Supporting copy also sits on the deeper, translucent nested-card tone.
    inkSecondary: '#64596B',
    inkWhisper: '#685E70',
    accent: palette.primary,
    accentBright: '#685093',
    accentGlow: palette.lavender,
    ember: '#A24C41',
    tones: lightTones,
    ...overrides,
  };
  // Existing previews and older components consume these aliases.
  return {
    ...theme,
    bg: theme.page, cardBg: theme.pageAged, primary: theme.accent,
    highlight: theme.accentBright, glow: theme.accentGlow,
  };
}

export const themes = {
  hyrule: cover({ name: 'Memory Meadow', icon: '🌼' }),
  vigil: cover({
    name: 'Twilight Meadow', icon: '🌙',
    page: '#292538', pageAged: '#332C45', pageShadow: '#514560',
    pageGlow: '#3D3450', ink: palette.paper,
    inkSecondary: '#DDD1EB', inkWhisper: '#D3C5E1',
    accent: '#D1BDF4', accentBright: '#E1D1FB', accentGlow: '#514560',
    ember: '#F4B6A0',
    tones: {
      goldLeaf: '#FFD892', moss: '#B9DABD', mossDeep: '#A9CFA9',
      emberDeep: '#F4B6A0', royal: '#D1BDF4', rose: '#EDBACF',
    },
  }),
  sunlit: cover({
    name: 'Honey Meadow', icon: '☀️',
    page: '#FFF9EE', pageAged: '#F9F3E5', pageShadow: '#EBDCC2',
    pageGlow: '#FFF9EE', accent: '#866329', accentBright: '#785320',
    accentGlow: palette.gold,
  }),
  snowquill: cover({
    name: 'Cloud Meadow', icon: '☁️',
    page: '#F4FAFC', pageAged: '#EEF6FB', pageShadow: '#D4E6EE',
    pageGlow: '#F4FAFC', accent: '#486780', accentBright: '#3C586F',
    accentGlow: palette.sky,
  }),
  verdant: cover({
    name: 'Clover Meadow', icon: '🍀',
    page: '#F7FBF3', pageAged: '#F1F8F2', pageShadow: '#D6E6D8',
    pageGlow: '#F7FBF3', accent: '#486B55', accentBright: '#3C5C48',
    accentGlow: palette.mint,
  }),
  harvest: cover({
    name: 'Peach Meadow', icon: '🍑',
    page: '#FFF7F0', pageAged: '#FFF1E8', pageShadow: '#EED8D1',
    pageGlow: '#FFF7F0', accent: '#A24F6F', accentBright: '#8B405D',
    accentGlow: palette.accent,
  }),
};

export const LEGACY_THEME_ALIASES = {
  summer: 'sunlit', winter: 'snowquill', spring: 'verdant', autumn: 'harvest',
};

export function applyTheme(themeName) {
  const resolved = LEGACY_THEME_ALIASES[themeName] || themeName;
  const theme = themes[resolved] || themes.hyrule;
  const root = document.documentElement;
  const tokens = {
    'ink-page': theme.page, 'ink-page-aged': theme.pageAged,
    'ink-page-shadow': theme.pageShadow, 'ink-page-rune-glow': theme.pageGlow,
    'ink-primary': theme.ink, 'ink-secondary': theme.inkSecondary,
    'ink-whisper': theme.inkWhisper, 'sheikah-teal': theme.accentBright,
    'sheikah-teal-deep': theme.accent, ember: theme.ember,
    'gold-leaf': theme.tones.goldLeaf, moss: theme.tones.moss,
    'moss-deep': theme.tones.mossDeep, 'ember-deep': theme.tones.emberDeep,
    royal: theme.tones.royal, rose: theme.tones.rose,
    'forge-bg': theme.page, 'forge-card': theme.pageAged,
    'forge-border': theme.pageShadow, 'forge-muted': theme.pageShadow,
    'forge-text': theme.ink, 'forge-text-dim': theme.inkSecondary,
    'amber-primary': theme.accent, 'amber-highlight': theme.accentBright,
    'amber-glow': theme.accentGlow,
  };
  for (const [token, value] of Object.entries(tokens)) {
    root.style.setProperty(`--color-${token}`, value);
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme.page);
  // The body and portals inherit tokens through CSS; never paint body inline.
}

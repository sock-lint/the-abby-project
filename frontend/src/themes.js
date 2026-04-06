export const themes = {
  summer: {
    name: 'Summer',
    icon: '☀️',
    primary: '#d97706',
    highlight: '#f59e0b',
    glow: '#fbbf24',
    cardBg: '#1a1a1a',
    bg: '#0a0a0a',
  },
  winter: {
    name: 'Winter Break',
    icon: '❄️',
    primary: '#2563eb',
    highlight: '#60a5fa',
    glow: '#93c5fd',
    cardBg: '#0f172a',
    bg: '#020617',
  },
  spring: {
    name: 'Spring Break',
    icon: '🌸',
    primary: '#16a34a',
    highlight: '#4ade80',
    glow: '#86efac',
    cardBg: '#0a1a0a',
    bg: '#040d04',
  },
  autumn: {
    name: 'Autumn',
    icon: '🍂',
    primary: '#c2410c',
    highlight: '#f97316',
    glow: '#fdba74',
    cardBg: '#1c1008',
    bg: '#0d0804',
  },
};

export function applyTheme(themeName) {
  const theme = themes[themeName] || themes.summer;
  const root = document.documentElement;
  root.style.setProperty('--color-amber-primary', theme.primary);
  root.style.setProperty('--color-amber-highlight', theme.highlight);
  root.style.setProperty('--color-amber-glow', theme.glow);
  root.style.setProperty('--color-forge-card', theme.cardBg);
  root.style.setProperty('--color-forge-bg', theme.bg);
  document.body.style.background = theme.bg;
}

import { LEGACY_THEME_ALIASES, themes } from '../themes';

// Palette names are presentation; saved catalog identities stay compatible.
export function itemDisplayName(item) {
  if (item?.item_type === 'cosmetic_theme') {
    const key = item.metadata?.theme;
    const theme = themes[LEGACY_THEME_ALIASES[key] || key];
    if (theme) return theme.name;
  }
  return item?.name || '';
}

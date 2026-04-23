import { useCallback } from 'react';
import RpgSprite from '../../components/rpg/RpgSprite';
import { RARITY_TEXT_COLORS } from '../../constants/colors';
import { RARITY_HALO } from '../achievements/mastery.constants';
import { applyTheme } from '../../themes';
import { cosmeticLockHint } from './character.constants';

/**
 * CosmeticSigil — a single cosmetic tile inside a CosmeticChapter.
 *
 * Three states:
 *   • equipped  — RARITY_HALO + "equipped" gilt ribbon; click unequips.
 *   • owned     — clean parchment tile with rarity ring; click equips.
 *   • locked    — debossed intaglio (grayscale icon, inset shadow) + a
 *                  script unlock hint beneath the name. Not clickable.
 *
 * Theme-cover special case: when `slot === "active_theme"` the tile
 * hovers fire a transient `applyTheme(item.metadata.theme)` so the user
 * can feel a cover before committing. Release restores the current theme.
 * Disabled when the user prefers reduced motion (the cover shift can be
 * jarring for users with vestibular sensitivity).
 */
export default function CosmeticSigil({
  entry,
  slot,
  currentThemeName,
  onEquip,
  onUnequip,
  busy = false,
}) {
  const { item, owned, equipped } = entry;
  const rarity = item.rarity || 'common';

  const isThemeSlot = slot === 'active_theme';
  const themeName = isThemeSlot
    ? (item.metadata?.theme || item.metadata?.name || slugFromName(item.name))
    : null;

  const handleHover = useCallback(() => {
    if (!isThemeSlot || !themeName || !owned) return;
    if (typeof window === 'undefined') return;
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion) return;
    applyTheme(themeName);
  }, [isThemeSlot, themeName, owned]);

  const handleLeave = useCallback(() => {
    if (!isThemeSlot || !themeName) return;
    if (typeof window === 'undefined') return;
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reducedMotion) return;
    applyTheme(currentThemeName || 'hyrule');
  }, [isThemeSlot, themeName, currentThemeName]);

  const handleClick = () => {
    if (busy) return;
    if (!owned) return;
    if (equipped) {
      onUnequip?.(slot);
    } else {
      onEquip?.(item.id);
    }
  };

  const accessibleName = !owned
    ? `${item.name} · ${rarity} · not yet owned`
    : equipped
    ? `${item.name} · ${rarity} · currently equipped — click to remove`
    : `${item.name} · ${rarity} · click to equip`;

  const shellBase =
    'relative w-full rounded-2xl p-3 flex flex-col items-center gap-1.5 min-h-[136px] transition-transform';
  const shellEarned = `bg-ink-page-rune-glow/95 border border-ink-page-shadow ${
    equipped ? RARITY_HALO[rarity] || RARITY_HALO.common : ''
  }`;
  const shellLocked =
    'border border-dashed border-ink-whisper/30 bg-ink-page-aged/40 text-ink-whisper/60 shadow-[inset_0_2px_6px_-2px_rgba(45,31,21,0.25),inset_0_-1px_0_rgba(255,248,224,0.4)]';

  const body = (
    <div
      data-cosmetic-sigil="true"
      data-owned={owned ? 'true' : 'false'}
      data-equipped={equipped ? 'true' : 'false'}
      data-rarity={rarity}
      className={`${shellBase} ${owned ? shellEarned : shellLocked} ${
        owned ? 'active:scale-[0.98]' : ''
      }`}
    >
      <div
        className={`relative w-14 h-14 rounded-full flex items-center justify-center ${
          owned
            ? 'bg-ink-page-aged shadow-[inset_0_1px_0_rgba(255,248,224,0.6),inset_0_-2px_4px_rgba(45,31,21,0.15)]'
            : 'bg-ink-page-shadow/25 shadow-[inset_0_2px_4px_rgba(45,31,21,0.35),inset_0_-1px_0_rgba(255,248,224,0.25)]'
        }`}
      >
        <div className={owned ? '' : 'grayscale opacity-45'}>
          <RpgSprite
            spriteKey={item.sprite_key}
            icon={item.icon}
            size={32}
            alt={item.name}
          />
        </div>
      </div>

      <div
        className={`text-caption text-center font-medium leading-tight line-clamp-2 ${
          owned ? 'text-ink-primary' : 'text-ink-whisper/75'
        }`}
      >
        {item.name}
      </div>
      <div
        className={`text-micro font-rune uppercase tracking-wider ${
          owned ? (RARITY_TEXT_COLORS[rarity] || 'text-ink-secondary') : 'text-ink-whisper/55'
        }`}
      >
        {rarity}
      </div>

      {!owned && (
        <div
          data-cosmetic-hint="true"
          className="mt-0.5 text-micro italic font-script text-center leading-snug text-ink-whisper/80 line-clamp-2 px-1"
        >
          {cosmeticLockHint(item)}
        </div>
      )}

      {equipped && (
        <div
          data-cosmetic-equipped-ribbon="true"
          className="mt-auto pt-1 text-micro font-rune uppercase tracking-wider text-gold-leaf"
        >
          equipped
        </div>
      )}
    </div>
  );

  if (!owned) {
    return (
      <div
        aria-label={accessibleName}
        role="img"
        className="w-full"
      >
        {body}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      onMouseEnter={handleHover}
      onMouseLeave={handleLeave}
      onFocus={handleHover}
      onBlur={handleLeave}
      disabled={busy}
      aria-label={accessibleName}
      aria-pressed={equipped}
      className="w-full focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal rounded-2xl disabled:opacity-70"
    >
      {body}
    </button>
  );
}

function slugFromName(name = '') {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

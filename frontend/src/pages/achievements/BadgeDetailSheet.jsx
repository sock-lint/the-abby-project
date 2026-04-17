import BottomSheet from '../../components/BottomSheet';
import { RARITY_PILL_COLORS, RARITY_TEXT_COLORS } from '../../constants/colors';
import { RARITY_HALO } from './mastery.constants';

/**
 * BadgeDetailSheet — illuminated detail pane for a single sigil. Mirrors
 * SkillDetailSheet's composition: hero glyph in an ornate ring, rarity
 * ribbon, description, earned-at (sealed on {date}) or "not yet earned"
 * chip, optional XP bonus line.
 */
export default function BadgeDetailSheet({ entry, onClose }) {
  const { badge, earned, earnedAt } = entry;
  const rarity = badge.rarity || 'common';

  return (
    <BottomSheet title={badge.name} onClose={onClose}>
      <div className="space-y-4">
        {/* Hero sigil */}
        <div className="flex flex-col items-center text-center">
          <div
            className={`relative w-24 h-24 rounded-full border-2 border-ink-page-shadow flex items-center justify-center bg-ink-page-rune-glow shadow-[0_0_0_4px_var(--color-ink-page-aged),0_0_0_5px_var(--color-ink-page-shadow)] ${
              earned ? RARITY_HALO[rarity] || RARITY_HALO.common : ''
            }`}
          >
            <span aria-hidden="true" className={`text-5xl leading-none ${earned ? '' : 'grayscale opacity-50'}`}>
              {badge.icon || '🏅'}
            </span>
          </div>

          <div
            className={`mt-3 inline-flex items-center gap-1 rounded-full px-3 py-1 text-micro font-rune uppercase tracking-wider ${
              RARITY_PILL_COLORS[rarity] || RARITY_PILL_COLORS.common
            }`}
          >
            {rarity}
          </div>

          {badge.description && (
            <p className="mt-3 text-body text-ink-whisper max-w-prose">
              {badge.description}
            </p>
          )}
        </div>

        {badge.xp_bonus > 0 && (
          <div className="flex items-center justify-center gap-2 rounded-xl border border-sheikah-teal/30 bg-sheikah-teal/5 px-3 py-2">
            <span className="font-rune text-caption uppercase tracking-wider text-sheikah-teal-deep">
              bonus ink
            </span>
            <span className="font-display text-lede font-bold text-sheikah-teal-deep">
              +{badge.xp_bonus} XP
            </span>
          </div>
        )}

        <div className="text-center">
          {earned ? (
            <div className={`font-script text-lede ${RARITY_TEXT_COLORS[rarity] || 'text-ink-primary'}`}>
              {`sealed ${formatSealDate(earnedAt)}`}
            </div>
          ) : (
            <div className="font-script italic text-ink-whisper">
              not yet earned
            </div>
          )}
        </div>
      </div>
    </BottomSheet>
  );
}

function formatSealDate(iso) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return '';
  }
}

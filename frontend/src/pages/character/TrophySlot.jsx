import { RARITY_PILL_COLORS } from '../../constants/colors';
import { RARITY_HALO } from '../achievements/mastery.constants';

/**
 * TrophySlot — the hero seal on the Frontispiece. A big wax-seal button:
 *
 *   • With a trophy set: renders the badge icon inside a rarity-haloed
 *     parchment roundel, name in display-serif, a small "hero seal"
 *     script caption. Click opens the picker (to change or clear).
 *   • Without a trophy: a debossed intaglio with a script hint inviting
 *     the user to choose one. Click opens the picker.
 *
 * The slot is the page's signature moment — it turns an otherwise-static
 * dashboard into an act of self-expression. Click handler delegated to
 * the parent so the picker (a BottomSheet) lives at page scope and can
 * re-fetch on select without needing to hoist that state here.
 */
export default function TrophySlot({ badge, onOpen }) {
  const rarity = badge?.rarity || 'common';
  const accessibleName = badge
    ? `Hero seal: ${badge.name}. Click to change or clear.`
    : 'No hero seal chosen — click to pick one from your reliquary.';

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={accessibleName}
      data-trophy-slot="true"
      data-filled={badge ? 'true' : 'false'}
      className="group relative flex flex-col items-center gap-2 text-center focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal rounded-2xl p-2 transition-transform hover:-translate-y-0.5 active:scale-[0.98]"
    >
      <div
        className={`relative w-20 h-20 rounded-full border-2 border-ink-page-shadow flex items-center justify-center ${
          badge
            ? `bg-ink-page-rune-glow ${RARITY_HALO[rarity] || RARITY_HALO.common} shadow-[0_0_0_3px_var(--color-ink-page-aged),0_0_0_4px_var(--color-ink-page-shadow)]`
            : 'bg-ink-page-shadow/30 shadow-[inset_0_3px_6px_rgba(45,31,21,0.35),inset_0_-1px_0_rgba(255,248,224,0.3)]'
        }`}
      >
        {badge ? (
          <span aria-hidden="true" className="text-4xl leading-none">
            {badge.icon || '\ud83c\udfc5'}
          </span>
        ) : (
          <span
            aria-hidden="true"
            className="text-3xl leading-none grayscale opacity-40"
          >
            {'\ud83d\udd8b\ufe0f'}
          </span>
        )}
      </div>

      {badge ? (
        <>
          <div
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-micro font-rune uppercase tracking-wider ${
              RARITY_PILL_COLORS[rarity] || RARITY_PILL_COLORS.common
            }`}
          >
            {rarity}
          </div>
          <div className="font-display text-caption italic text-ink-primary leading-tight max-w-[10rem] line-clamp-2">
            {badge.name}
          </div>
          <div className="font-script text-micro text-ink-whisper/80 leading-tight">
            your hero seal
          </div>
        </>
      ) : (
        <>
          <div className="font-script text-caption text-ink-whisper leading-tight">
            no hero seal chosen
          </div>
          <div className="font-script text-micro text-sheikah-teal-deep underline decoration-dotted underline-offset-2 opacity-70 group-hover:opacity-100 transition-opacity">
            choose from your reliquary
          </div>
        </>
      )}
    </button>
  );
}

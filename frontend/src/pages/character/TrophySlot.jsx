import { Award } from 'lucide-react';
import { RARITY_PILL_COLORS } from '../../constants/colors';
import { RARITY_HALO } from '../../components/atlas/mastery.constants';

/**
 * TrophySlot — the featured badge on the Frontispiece.
 *
 *   • With a trophy set: a soft icon well, rarity ring and badge name.
 *     Click opens the picker (to change or clear).
 *   • Without a trophy: a dashed well with a readable hint inviting
 *     the user to choose one. Click opens the picker.
 *
 * The slot is the page's signature moment — it turns an otherwise-static
 * dashboard into an act of self-expression. Click handler delegated to
 * the parent so the picker (a BottomSheet) lives at page scope and can
 * re-fetch on select without needing to hoist that state here.
 */
export default function TrophySlot({ badge, onOpen, compact = false }) {
  const rarity = badge?.rarity || 'common';
  const accessibleName = badge
    ? `Trophy badge: ${badge.name}. Click to change or clear.`
    : 'No trophy badge chosen — choose an earned badge.';

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={accessibleName}
      data-trophy-slot="true"
      data-filled={badge ? 'true' : 'false'}
      className={`group relative flex items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl p-2 transition-transform hover:-translate-y-0.5 active:scale-[0.98] ${compact ? 'w-full text-left border border-ink-page-shadow bg-ink-page-aged' : 'flex-col text-center'}`}
    >
      <div
        className={`relative shrink-0 border border-ink-page-shadow flex items-center justify-center ${compact ? 'w-11 h-11 rounded-xl' : 'w-20 h-20 rounded-3xl'} ${
          badge
            ? `bg-ink-page-aged ${RARITY_HALO[rarity] || RARITY_HALO.common}`
            : 'border-dashed bg-ink-page/70'
        }`}
      >
        {badge ? (
          <span aria-hidden="true" className={`${compact ? 'text-2xl' : 'text-4xl'} leading-none`}>
            {badge.icon || '\ud83c\udfc5'}
          </span>
        ) : (
          <Award size={compact ? 24 : 32} aria-hidden="true" className="text-ink-whisper" />
        )}
      </div>

      {compact ? (
        <span className="min-w-0 flex-1">
          <span className="block font-body text-caption text-ink-secondary">Your trophy badge</span>
          <span className="block font-body font-bold text-body text-ink-primary break-words">
            {badge?.name || 'Choose an earned badge'}
          </span>
          {badge && <span className="block font-body text-tiny text-ink-secondary">{rarity}</span>}
        </span>
      ) : badge ? (
        <>
          <div
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-caption font-body font-semibold ${
              RARITY_PILL_COLORS[rarity] || RARITY_PILL_COLORS.common
            }`}
          >
            {rarity}
          </div>
          <div className="font-body font-bold text-body text-ink-primary leading-tight max-w-[10rem] line-clamp-2">
            {badge.name}
          </div>
          <div className="font-body text-caption text-ink-whisper leading-tight">
            Your trophy badge
          </div>
        </>
      ) : (
        <>
          <div className="font-body text-caption text-ink-whisper leading-tight">
            No trophy badge chosen
          </div>
          <div className="font-body text-caption text-sheikah-teal-deep underline decoration-dotted underline-offset-2 group-hover:decoration-solid">
            Choose an earned badge
          </div>
        </>
      )}
      {compact && <span aria-hidden="true" className="font-body text-caption text-sheikah-teal-deep">{badge ? 'Change' : 'Choose'}</span>}
    </button>
  );
}

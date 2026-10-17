import { Award } from 'lucide-react';
import BadgeArtwork from '../../components/atlas/BadgeArtwork';
import BadgeRarity from '../../components/atlas/BadgeRarity';

/**
 * TrophySlot — the featured badge on the Frontispiece.
 *
 *   • With a trophy set: a gold-framed icon, rarity ring and badge name.
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
      className={`group relative flex min-w-0 max-w-full items-center gap-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl p-2 transition-transform hover:-translate-y-0.5 active:scale-[0.98] ${compact ? 'w-full text-left border border-ink-page-shadow bg-ink-page-aged' : 'flex-col text-center'}`}
    >
      {badge ? (
        <BadgeArtwork badge={badge} earned variant="featured" size={compact ? 'md' : 'lg'} />
      ) : (
        <span className={`relative shrink-0 border border-dashed border-ink-page-shadow bg-ink-page/70 flex items-center justify-center ${compact ? 'size-11 rounded-xl' : 'size-20 rounded-3xl'}`}>
          <Award size={compact ? 24 : 32} aria-hidden="true" className="text-ink-whisper" />
        </span>
      )}

      {compact ? (
        <span className="min-w-0 flex-1">
          <span className="block font-body text-caption text-ink-secondary">Your trophy badge</span>
          <span className="block font-body font-bold text-body text-ink-primary break-words [overflow-wrap:anywhere]">
            {badge?.name || 'Choose an earned badge'}
          </span>
          {badge && <span className="mt-1 block"><BadgeRarity rarity={rarity} /></span>}
        </span>
      ) : badge ? (
        <>
          <BadgeRarity rarity={rarity} />
          <div className="min-w-0 font-body font-bold text-body text-ink-primary leading-tight max-w-[10rem] break-words [overflow-wrap:anywhere] line-clamp-2">
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
      {compact && <span aria-hidden="true" className="shrink-0 font-body text-caption text-sheikah-teal-deep">{badge ? 'Change' : 'Choose'}</span>}
    </button>
  );
}

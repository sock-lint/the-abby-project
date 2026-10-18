import { Award } from 'lucide-react';
import AchievementCard from '../../components/cards/AchievementCard';
import BadgeArtwork from '../../components/atlas/BadgeArtwork';
import BadgeRarity from '../../components/atlas/BadgeRarity';

/** The earned badge keeps its real identity inside the kit's compact canvas.
 * The whole card is one picker button; decorative layers add no focus targets. */
export default function TrophySlot({ badge, onOpen, compact = false }) {
  const rarity = badge?.rarity || 'common';
  const accessibleName = badge
    ? `Trophy badge: ${badge.name}. Click to change or clear.`
    : 'No trophy badge chosen — choose an earned badge.';

  return (
    <AchievementCard
      as="button"
      variant="wide"
      type="button"
      onClick={onOpen}
      aria-label={accessibleName}
      data-trophy-slot="true"
      data-filled={badge ? 'true' : 'false'}
      className="group w-full max-w-md text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep transition-transform hover:-translate-y-0.5 active:scale-[0.98]"
      contentClassName="flex flex-wrap items-start gap-3"
    >
      {badge ? (
        <BadgeArtwork badge={badge} earned size={compact ? 'sm' : 'md'} />
      ) : (
        <span className="relative size-14 shrink-0 rounded-2xl border border-dashed border-ink-page-shadow bg-ink-page/70 flex items-center justify-center">
          <Award size={28} aria-hidden="true" className="text-ink-whisper" />
        </span>
      )}
      <span data-trophy-copy="true" className="flex-1 basis-[9em] min-w-[min(100%,9em)] text-body">
        <span className="block font-body text-caption text-ink-secondary">Your trophy badge</span>
        <span className="block font-body font-bold text-body text-ink-primary break-words [overflow-wrap:anywhere]">
          {badge?.name || 'Choose an earned badge'}
        </span>
        {badge && <span className="mt-1 block"><BadgeRarity rarity={rarity} /></span>}
        <span aria-hidden="true" className="mt-2 block font-body text-caption text-sheikah-teal-deep">{badge ? 'Change' : 'Choose'}</span>
      </span>
    </AchievementCard>
  );
}

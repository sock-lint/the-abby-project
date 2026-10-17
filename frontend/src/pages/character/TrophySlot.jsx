import { Award } from 'lucide-react';
import BadgeArtwork from '../../components/atlas/BadgeArtwork';
import BadgeRarity from '../../components/atlas/BadgeRarity';
import CardStyleArtwork from './CardStyleArtwork';
import { cardStyleForFrame } from './cardStylePresentation';

/** The equipped frame supplies decoration; the saved earned badge supplies
 * identity. The original button opens the trophy chooser in every state. */
export default function TrophySlot({ badge, frame, onOpen, compact = false }) {
  const rarity = badge?.rarity || 'common';
  const cardStyle = cardStyleForFrame(frame);
  const accessibleName = badge
    ? `Trophy badge: ${badge.name}. Click to change or clear.`
    : 'No trophy badge chosen — choose an earned badge.';

  return <button type="button" onClick={onOpen} aria-label={accessibleName}
    data-trophy-slot="true" data-filled={badge ? 'true' : 'false'}
    data-frame-card-style={cardStyle?.assetId}
    className={`profile-trophy group relative min-w-0 max-w-full rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep ${compact ? 'w-full' : 'profile-trophy--full'}`}>
    <CardStyleArtwork frame={frame} className="profile-trophy__art" />
    <span data-trophy-copy="true" className="profile-trophy__copy">
      <span className="profile-trophy__identity">
        {badge ? <BadgeArtwork badge={badge} earned /> : <span aria-hidden="true"
          className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-dashed border-ink-page-shadow bg-ink-page/70">
          <Award size={28} className="text-ink-whisper" />
        </span>}
        <span className="profile-trophy__identity-copy">
          <span className="block font-body text-caption text-ink-secondary">Your trophy badge</span>
          <span className="mt-1 block break-words [overflow-wrap:anywhere] font-body text-lede font-bold leading-snug text-ink-primary">
            {badge?.name || 'Choose an earned badge'}
          </span>
          {badge && <span className="mt-2 block"><BadgeRarity rarity={rarity} /></span>}
        </span>
      </span>
      {cardStyle && <span data-profile-card-label="true" className="mt-3 block font-body text-caption text-ink-secondary">
        {cardStyle.label}
      </span>}
      <span aria-hidden="true" className="mt-3 block font-body text-caption font-semibold text-sheikah-teal-deep">{badge ? 'Change' : 'Choose'}</span>
    </span>
  </button>;
}

import ArtworkImage from '../rpg/ArtworkImage';

/** The selected earned badge, using its actual catalog artwork and a readable fallback. */
export default function FeaturedBadge({ badge, compact = false, chip = false, className = '' }) {
  if (!badge) return null;
  return <span className={`${chip ? 'featured-badge-chip' : `inline-flex min-w-0 items-center gap-1.5 ${compact ? 'shrink-0' : ''}`} ${className}`}
    role={compact || chip ? 'img' : undefined} aria-label={compact || chip ? `Featured badge: ${badge.name}` : undefined}>
    <span aria-hidden="true" className={chip ? 'featured-badge-chip__icon' : `inline-flex shrink-0 items-center justify-center rounded-full border border-gold-leaf/40 bg-ink-page-aged ${compact ? 'size-5' : 'size-6'}`}>
      <ArtworkImage assetId={badge.catalog_icon} fallback={badge.icon || '🏅'} size={compact ? 14 : 18} />
    </span>
    {!compact && <span className={chip ? 'featured-badge-chip__text' : 'min-w-0 break-words text-caption text-ink-secondary'}>{badge.name}</span>}
  </span>;
}

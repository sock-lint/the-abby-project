import ArtworkImage from '../rpg/ArtworkImage';

/** The selected earned badge, using its actual catalog artwork and a readable fallback. */
export default function FeaturedBadge({ badge, compact = false, className = '' }) {
  if (!badge) return null;
  return <span className={`inline-flex min-w-0 items-center gap-1.5 ${compact ? 'shrink-0' : ''} ${className}`}
    role={compact ? 'img' : undefined} aria-label={compact ? `Featured badge: ${badge.name}` : undefined}>
    <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center rounded-full border border-gold-leaf/40 bg-ink-page-aged ${compact ? 'size-5' : 'size-6'}`}>
      <ArtworkImage assetId={badge.catalog_icon} fallback={badge.icon || '🏅'} size={compact ? 14 : 18} />
    </span>
    {!compact && <span className="min-w-0 break-words text-caption text-ink-secondary">{badge.name}</span>}
  </span>;
}

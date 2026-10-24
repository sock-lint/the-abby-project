import CharacterTitle from './CharacterTitle';
import FeaturedBadge from './FeaturedBadge';

/** Saved title and featured achievement keep their artwork and accessible names. */
export default function IdentityChips({ title, badge, compact = false, className = '' }) {
  if (!title && !badge) return null;
  return <span className={`identity-chips ${compact ? 'identity-chips--compact' : ''} ${className}`} data-identity-chips="true">
    <CharacterTitle title={title} compact={compact} />
    <FeaturedBadge badge={badge} chip compact={compact} />
  </span>;
}

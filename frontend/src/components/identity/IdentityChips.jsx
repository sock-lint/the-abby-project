import CharacterTitle from './CharacterTitle';
import FeaturedBadge from './FeaturedBadge';

/** Saved title and featured achievement keep their own artwork and full names. */
export default function IdentityChips({ title, badge, className = '' }) {
  if (!title && !badge) return null;
  return <span className={`identity-chips ${className}`} data-identity-chips="true">
    <CharacterTitle title={title} />
    <FeaturedBadge badge={badge} chip />
  </span>;
}

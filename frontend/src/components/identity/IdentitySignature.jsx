import ProfilePortrait from './ProfilePortrait';
import CharacterTitle from './CharacterTitle';
import FeaturedBadge from './FeaturedBadge';

/** A saved identity shared by Today and family-visible project signatures. */
export default function IdentitySignature({ identity, prefix = '', portraitSize = 'md' }) {
  if (!identity) return null;
  const name = identity.display_name || identity.username;
  return <div className="flex min-w-0 items-center gap-3">
    <ProfilePortrait name={name} avatar={identity.avatar} frame={identity.active_frame} size={portraitSize} />
    <div className="min-w-0 flex-1 space-y-1">
      <p className="break-words font-body font-semibold text-body text-ink-primary">{prefix ? `${prefix} ${name}` : name}</p>
      <CharacterTitle title={identity.active_title} />
      <FeaturedBadge badge={identity.active_trophy_badge} />
    </div>
  </div>;
}

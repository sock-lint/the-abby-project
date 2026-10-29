import { Link } from 'react-router-dom';

export default function DiscoveryAcquisitionHint({ offer }) {
  return <div className="space-y-2">
    <p className="text-body text-ink-secondary">Choose one egg discovery and work toward it through reading, movement, and making or practice. Its compatible potion and starter food are included.</p>
    {offer ? <p className="text-caption text-ink-secondary">{offer.eligible
      ? `${offer.name} is available to choose.`
      : offer.unavailable_reason || 'This discovery is not available to start right now.'}</p>
      : <p className="text-caption text-ink-secondary">This appearance has no discovery available to start right now.</p>}
    <Link className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep"
      to={offer?.path || '/quests?tab=trials'}>View egg discoveries</Link>
  </div>;
}

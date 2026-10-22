import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { useAuth } from '../../hooks/useApi';
import { usePulse } from '../../providers/pulseContext';
import IdentitySignature from '../identity/IdentitySignature';
import { identityForUser } from '../identity/identity';

export default function TodayIdentity({ identity: dashboardIdentity }) {
  const { user } = useAuth();
  const { pulse } = usePulse();
  const identity = identityForUser(pulse && Object.hasOwn(pulse, 'identity') ? pulse.identity : dashboardIdentity, user);
  if (!identity) return null;
  return <section aria-label="Your look">
    <Link to="/sigil" className="flex min-w-0 items-center justify-between gap-3 rounded-2xl border border-ink-page-shadow bg-ink-page-aged px-4 py-3 transition-colors hover:bg-ink-page-rune-glow focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sheikah-teal-deep">
      <IdentitySignature identity={identity} />
      <ChevronRight size={16} className="shrink-0 text-sheikah-teal-deep" aria-hidden="true" />
    </Link>
  </section>;
}

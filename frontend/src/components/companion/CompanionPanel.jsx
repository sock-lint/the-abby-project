import { Link } from 'react-router-dom';
import { getStable } from '../../api';
import { useApi, useAuth } from '../../hooks/useApi';
import { preferredCompanion } from '../../companion/appearance';
import CompanionPreview from './CompanionPreview';
import ErrorAlert from '../ErrorAlert';

export default function CompanionPanel() {
  const { user } = useAuth();
  return user ? <OwnedCompanion key={user.id} /> : null;
}

function OwnedCompanion() {
  const { data, loading, error, reload } = useApi(getStable);
  const active = preferredCompanion(data);
  return (
    <div className="space-y-3">
      {loading ? <p className="text-body text-ink-secondary" role="status">Finding your companion…</p>
        : error && !data ? <ErrorAlert message={error} onRetry={reload} />
          : <CompanionPreview creature={active?.creature} kind={active?.kind}>
            <nav className="companion-feature-links" aria-label="Companion actions">
              <Link to="/bestiary?tab=companions">Care & choose pets</Link>
              <Link to="/bestiary?tab=hatchery">Hatch & breed</Link>
              <Link to="/bestiary?tab=mounts">Grown pets & expeditions</Link>
              <Link to="/treasury?tab=satchel">Inventory</Link>
            </nav>
          </CompanionPreview>}
    </div>
  );
}

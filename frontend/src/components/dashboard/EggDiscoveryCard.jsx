import { Link } from 'react-router-dom';
import useEggDiscoveries from '../../hooks/useEggDiscoveries';
import ParchmentCard from '../journal/ParchmentCard';
import CatalogIcon from '../rpg/CatalogIcon';
import ErrorAlert from '../ErrorAlert';
import DiscoveryProgress from '../egg-discovery/DiscoveryProgress';

export default function EggDiscoveryCard({ refreshKey }) {
  const state = useEggDiscoveries({ refreshKey });
  if (!state.allowed || state.loading || (!state.enabled && !state.error)) return null;
  if (!state.enabled) return <ErrorAlert message={state.error} onRetry={state.reload} />;
  const active = state.data.discoveries.find((row) => row.id === state.data.active_id && row.status === 'active');
  return <ParchmentCard>
    <section aria-label="Your egg discovery" className="space-y-3">
      <p className="text-caption font-semibold text-sheikah-teal-deep">Egg discovery preview</p>
      <ErrorAlert message={state.error} onRetry={state.reload} />
      {active ? <>
        <div className="flex items-center gap-3"><CatalogIcon spriteKey={active.egg_item?.sprite_key} icon={active.egg_item?.icon || '🥚'} size={40} alt="Egg" /><h2 className="font-semibold text-lede text-ink-primary break-words">{active.name}</h2></div>
        <DiscoveryProgress discovery={active} compact />
      </> : <p className="text-body text-ink-secondary">Choose one egg to work toward through your activities.</p>}
      <Link to="/quests?tab=trials" className="inline-flex min-h-11 items-center font-semibold text-body text-sheikah-teal-deep">{active ? 'View egg discovery' : 'Choose an egg'}</Link>
    </section>
  </ParchmentCard>;
}

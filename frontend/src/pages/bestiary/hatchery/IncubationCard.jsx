import { useEffect, useState } from 'react';
import Button from '../../../components/Button';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import { formatExpeditionRemaining } from '../party/party.constants';

function useRemainingSeconds(seconds, snapshotKey) {
  const total = Number.isFinite(seconds) ? Math.max(0, seconds) : null;
  const [clock, setClock] = useState({ total, snapshotKey, remaining: total });
  if (clock.total !== total || clock.snapshotKey !== snapshotKey) {
    setClock({ total, snapshotKey, remaining: total });
  }
  useEffect(() => {
    if (total === null || total <= 0) return;
    // Monotonic elapsed time keeps a changed device clock from skipping the
    // displayed wait. Even at zero, only the server can enable hatching.
    const startedAt = performance.now();
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.ceil(total - (performance.now() - startedAt) / 1000));
      setClock({ total, snapshotKey, remaining });
      if (remaining === 0) clearInterval(timer);
    }, 1000);
    return () => clearInterval(timer);
  }, [total, snapshotKey]);
  return clock.remaining;
}

export default function IncubationCard({ egg, potion, remainingSeconds, isReady, snapshotKey, working, refreshing, blocked, onHatch, onRefresh }) {
  const remaining = useRemainingSeconds(remainingSeconds, snapshotKey);
  return <ParchmentCard>
    <section aria-label="Your incubating egg" className="space-y-3">
      <div aria-live="polite"><h3 className="font-display font-bold text-lede text-ink-primary">{isReady ? 'Your egg is ready to hatch' : 'Your egg is incubating'}</h3></div>
      <p className="text-body text-ink-primary">{egg?.icon || '🥚'} {egg?.name || 'Your egg'}{potion?.name ? ` · ${potion.name}` : ''}</p>
      {!isReady && <p className="text-body text-ink-secondary">{remaining > 0
        ? `Ready to hatch in ${formatExpeditionRemaining(remaining)}.`
        : 'Checking whether your egg is ready…'}</p>}
      <p className="text-caption text-ink-secondary">{isReady
        ? 'Hatch your baby when you are ready, then help it grow with care.'
        : 'Your egg keeps incubating while you are away. One egg can incubate at a time.'}</p>
      {isReady ? <Button onClick={onHatch} disabled={working || refreshing || blocked}>{working ? 'Hatching…' : 'Hatch pet'}</Button>
        : <Button variant="secondary" onClick={onRefresh} disabled={working || refreshing}>{refreshing ? 'Checking…' : 'Check readiness'}</Button>}
    </section>
  </ParchmentCard>;
}

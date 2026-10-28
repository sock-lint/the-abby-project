import { useSpace } from '../../hooks/useSpace';
import useParentPendingCounts from '../../hooks/useParentPendingCounts';

export default function SpaceSwitcher() {
  const { space, isParentAccount, switchSpace, switchBlocked } = useSpace();
  const { total, ready, incomplete } = useParentPendingCounts({ enabled: isParentAccount });
  if (!isParentAccount) return null;
  const badge = !ready ? '…' : incomplete ? '?' : total > 9 ? '9+' : total || null;
  const attention = !ready ? 'Checking family reviews' : incomplete
    ? 'Some family review queues are unavailable' : `${total} family items needing attention`;
  return <div className="px-4 lg:px-6 pb-2 lg:pb-3 space-y-1">
    <div role="group" aria-label="Choose your space" className="flex max-w-64 lg:max-w-md rounded-2xl bg-sheikah-teal/10 p-0.5 lg:p-1 gap-1">
      {[['family', 'Family'], ['personal', 'My space']].map(([id, label]) => <button
        key={id} type="button" aria-pressed={space === id}
        disabled={switchBlocked && space !== id}
        aria-describedby={switchBlocked ? 'space-switch-help' : undefined}
        onClick={() => { if (space !== id) switchSpace(id); }}
        className={`flex flex-1 items-center justify-center gap-2 min-h-11 px-2 lg:px-3 py-2 rounded-xl font-body font-bold text-body transition-colors disabled:opacity-50 ${space === id ? 'bg-sheikah-teal-deep text-ink-page' : 'text-ink-primary hover:bg-sheikah-teal/10'}`}
      >{label}{id === 'family' && badge !== null && <span aria-label={attention}
        className="inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-ember-deep text-ink-page text-caption tabular-nums">{badge}</span>}</button>)}
    </div>
    {switchBlocked && <p id="space-switch-help" className="font-body text-caption text-ink-secondary">Save or close your current form before switching spaces.</p>}
  </div>;
}

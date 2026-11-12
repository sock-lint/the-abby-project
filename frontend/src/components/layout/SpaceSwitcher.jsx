import { useId } from 'react';
import { useSpace } from '../../hooks/useSpace';
import useParentPendingCounts from '../../hooks/useParentPendingCounts';
import Dropdown from '../form/Dropdown';

export default function SpaceSwitcher({ variant = 'desktop' }) {
  const { space, isParentAccount, switchSpace, switchBlocked } = useSpace();
  const { total, ready, incomplete } = useParentPendingCounts({ enabled: isParentAccount });
  const helpId = useId();
  const attentionId = useId();
  if (!isParentAccount) return null;
  const badge = !ready ? '…' : incomplete ? '?' : total > 9 ? '9+' : total || null;
  const attention = !ready ? 'Checking family reviews' : incomplete
    ? 'Some family review queues are unavailable' : `${total} family items needing attention`;
  const help = switchBlocked && <p id={helpId} className="basis-full order-last font-body text-caption text-ink-secondary">Save or close your current form before switching spaces.</p>;
  if (variant === 'mobile') return <div className="contents lg:hidden">
    <div data-space-switcher="mobile" className="identity-space-dropdown relative w-[8em] max-w-full shrink-0 text-body">
      <span aria-hidden="true" data-space-track className="pointer-events-none absolute inset-x-0 inset-y-2.5 rounded-full bg-sheikah-teal/10" />
      <Dropdown aria-label="Choose your space" value={space} aria-disabled={switchBlocked}
        aria-describedby={[switchBlocked ? helpId : null, badge !== null ? attentionId : null].filter(Boolean).join(' ') || undefined}
        onChange={event => switchSpace(event.target.value)}
        className="relative min-h-11 w-full rounded-full bg-transparent px-2 py-3 text-body font-body font-bold text-ink-primary">
        <option value="family">Family{badge !== null ? ` ${badge}` : ''}</option>
        <option value="personal">My space</option>
      </Dropdown>
      {badge !== null && <span id={attentionId} hidden>{attention}</span>}
    </div>
    {help}
  </div>;
  return <div className="hidden lg:block lg:col-span-full lg:pb-3 lg:space-y-1">
    <div data-space-switcher="desktop" role="group" aria-label="Choose your space" className="relative flex w-full max-w-md p-1 gap-1">
      <span aria-hidden="true" data-space-track className="pointer-events-none absolute inset-0 rounded-2xl bg-sheikah-teal/10" />
      {[['family', 'Family'], ['personal', 'My space']].map(([id, label]) => <button
        key={id} type="button" aria-pressed={space === id}
        disabled={switchBlocked && space !== id}
        aria-describedby={switchBlocked ? helpId : undefined}
        onClick={() => { if (space !== id) switchSpace(id); }}
        className={`group/space relative flex flex-1 min-w-0 items-center justify-center gap-2 min-h-11 px-3 py-2 rounded-xl font-body font-bold text-body disabled:opacity-50 ${space === id ? 'text-ink-page' : 'text-ink-primary'}`}
      ><span aria-hidden="true" data-space-pill className={`pointer-events-none absolute inset-0 rounded-xl transition-colors ${space === id ? 'bg-sheikah-teal-deep' : 'group-hover/space:bg-sheikah-teal/10'}`} />
      <span className="relative">{label}</span>{id === 'family' && badge !== null && <span aria-label={attention}
        className="relative inline-flex items-center justify-center min-w-5 h-5 px-1 rounded-full bg-ember-deep text-ink-page text-caption tabular-nums">{badge}</span>}</button>)}
    </div>
    {help}
  </div>;
}

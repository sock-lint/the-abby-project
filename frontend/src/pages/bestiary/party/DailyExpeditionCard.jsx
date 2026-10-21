import { useId } from 'react';
import { Backpack, Hourglass, Map as MapIcon, Check } from 'lucide-react';
import Button from '../../../components/Button';
import { formatExpeditionRemaining } from './party.constants';

export default function DailyExpeditionCard({ mount, name, working, onLaunch, onClaim, onRefresh }) {
  const headingId = useId();
  const expedition = mount.active_expedition?.status === 'active' ? mount.active_expedition : null;
  const returned = expedition?.is_ready === true;
  const rested = !expedition && mount.expedition_available === false;
  const sharedTrip = rested && mount.expedition_available_in_seconds === null;
  const unknown = !expedition && mount.expedition_available == null;
  const Icon = returned ? Backpack : expedition ? Hourglass : rested ? Check : MapIcon;
  const title = returned ? `${name} is back!` : expedition ? `${name} is exploring` : rested ? 'A good adventure today' : "Today's adventure";
  const message = returned ? 'Your finds are waiting. Collect them whenever you’re ready.'
    : expedition ? `Back in ${formatExpeditionRemaining(expedition.seconds_remaining)}. You can leave the app while they explore.`
      : sharedTrip ? 'Another appearance of this species has an expedition to finish. Collect that pet’s finds before starting another trip.'
        : rested ? 'This species has explored today. Come back tomorrow for another trip; you can still play together now.'
        : unknown ? 'Check expedition availability before choosing a trip.'
          : `Send ${name} exploring once a day, then return to see what they found.`;
  return <section aria-labelledby={headingId} className="rounded-2xl border border-ink-page-shadow bg-ink-page-aged p-4 space-y-3">
    <div className="flex items-start gap-3">
      <Icon size={22} className="shrink-0 text-sheikah-teal-deep mt-1" aria-hidden="true" />
      <div className="space-y-1"><h3 id={headingId} className="text-lede font-bold text-ink-primary">{title}</h3>
        <p className="text-body text-ink-secondary">{message}</p></div>
    </div>
    {returned ? <Button disabled={working} onClick={() => onClaim(expedition.id)}>{working ? 'Collecting…' : 'Collect your finds'}</Button>
      : expedition ? <Button variant="secondary" disabled={working} onClick={onRefresh}>Check their return</Button>
        : unknown ? <Button variant="secondary" disabled={working} onClick={onRefresh}>Check availability</Button>
          : !rested ? <Button disabled={working} onClick={() => onLaunch(mount)}>Choose an expedition</Button>
          : null}
    <p className="text-caption text-ink-secondary">All appearances of the same species share one expedition per day. No rush to collect.</p>
  </section>;
}

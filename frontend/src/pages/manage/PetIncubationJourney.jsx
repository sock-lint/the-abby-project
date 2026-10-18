import { formatIncubationWait, isSupportedIncubationPolicy } from './petIncubationPresentation';

const sources = new Set(['incubation_started', 'incubation_ready', 'hatch']);
const dayLabel = (day) => Number.isFinite(day) && day >= 0 ? `Day ${day}` : 'Day unrecorded';

export default function PetIncubationJourney({ events, policy, truncated = false }) {
  const receipts = Array.isArray(events) ? events.filter((event) => sources.has(event.source)) : [];
  const recordedPolicy = isSupportedIncubationPolicy(policy);
  return <section aria-label="Egg and hatch journey" className="space-y-2">
    <h4 className="font-semibold text-ink-primary">Egg and hatch events</h4>
    {receipts.length ? <ol aria-label="Incubation journey events" className="space-y-3">
      {receipts.map((event, index) => <li key={`${event.source}:${index}`} className="rounded-lg bg-ink-page-aged p-3 space-y-1">
        <p className="font-semibold text-ink-primary">{event.source === 'incubation_started' ? 'Incubation started'
          : event.source === 'incubation_ready' ? 'Egg ready' : recordedPolicy ? 'Hatch claimed' : 'Hatched companion'}</p>
        <p className="text-body text-ink-secondary">{dayLabel(event.day)} · {typeof event.target === 'string' && event.target ? event.target : 'Companion unrecorded'}</p>
        {event.source === 'incubation_started' && <p className="text-body text-ink-secondary">Recorded wait: {formatIncubationWait(event.duration_seconds)}. {Number.isFinite(event.ready_day) && event.ready_day >= 0 ? `Ready from ${dayLabel(event.ready_day)}.` : 'Ready day unrecorded.'}</p>}
        {event.source === 'incubation_ready' && <p className="text-body text-ink-secondary">{recordedPolicy ? 'Waiting for the next active care visit to hatch.' : 'A readiness event was recorded.'}</p>}
        {event.source === 'hatch' && <p className="text-body text-ink-secondary">{recordedPolicy ? 'The active care visit hatched this egg and added the baby companion.' : 'A companion hatch was recorded.'}</p>}
      </li>)}
    </ol> : <p className="text-body text-ink-secondary">No incubation or hatch events appear in this journey preview.</p>}
    {truncated && <p className="text-caption text-ink-secondary">The journey preview is bounded and may omit events.</p>}
  </section>;
}

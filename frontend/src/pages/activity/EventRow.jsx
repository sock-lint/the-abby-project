import { useState, useId } from 'react';
import { ChevronRight } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import BreakdownStrip from './BreakdownStrip';
import { categoryMeta } from './activity.constants';

/**
 * Generic row for one ActivityEvent.
 *
 * Shows: category icon, summary, actor→subject subtitle, delta pills
 * (coins / money / xp — only rendered when non-null), and an expandable
 * <BreakdownStrip> with the calculation math. One component handles every
 * ``event_type`` — the visual signal comes entirely from ``category`` via
 * ``CATEGORY_META`` in ``activity.constants.js``.
 */
export default function EventRow({ event }) {
  const [expanded, setExpanded] = useState(false);
  const bodyId = useId();
  const meta = categoryMeta(event.category);
  const Icon = meta.icon;
  const breakdown = event.context?.breakdown || [];
  const hasBreakdown = breakdown.length > 0;

  const time = new Date(event.occurred_at).toLocaleTimeString(undefined, {
    hour: 'numeric', minute: '2-digit',
  });

  const actorName = event.actor?.display_name;
  const subjectName = event.subject?.display_name;
  const subtitle = [
    actorName && `by ${actorName}`,
    subjectName && actorName !== subjectName && `for ${subjectName}`,
    subjectName && !actorName && subjectName,
  ].filter(Boolean).join(' · ');

  return (
    <ParchmentCard className="p-3">
      <div className="flex items-start gap-3">
        <div className={`flex-none rounded-lg p-2 ${meta.bg}`}>
          <Icon size={16} className={meta.accent} aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <p className="font-body text-body text-ink-primary truncate">
              {event.summary}
            </p>
            <span
              className="ml-auto flex-none text-tiny text-ink-whisper font-mono"
            >
              {time}
            </span>
          </div>
          {subtitle && (
            <p className="text-caption text-ink-secondary">{subtitle}</p>
          )}
          <div className="mt-1 flex flex-wrap gap-1 text-tiny font-mono">
            {event.coins_delta != null && (
              <span
                className={
                  `px-1.5 py-0.5 rounded ${
                    event.coins_delta >= 0 ? 'bg-gold-leaf/15 text-gold-leaf'
                                            : 'bg-ember/15 text-ember-deep'
                  }`
                }
              >
                {event.coins_delta >= 0 ? '+' : ''}{event.coins_delta} coins
              </span>
            )}
            {event.money_delta != null && Number(event.money_delta) !== 0 && (
              <span
                className={
                  `px-1.5 py-0.5 rounded ${
                    Number(event.money_delta) >= 0 ? 'bg-moss/15 text-moss'
                                                   : 'bg-ember/15 text-ember-deep'
                  }`
                }
              >
                {Number(event.money_delta) >= 0 ? '+' : ''}${event.money_delta}
              </span>
            )}
            {event.xp_delta != null && (
              <span className="px-1.5 py-0.5 rounded bg-sheikah-teal/15 text-sheikah-teal-deep">
                +{event.xp_delta} xp
              </span>
            )}
            <span className="px-1.5 py-0.5 rounded bg-ink-page-shadow/40 text-ink-secondary">
              {event.event_type}
            </span>
          </div>

          {hasBreakdown && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              aria-controls={bodyId}
              className="mt-1 inline-flex items-center gap-1 text-tiny text-ink-whisper hover:text-ink-primary"
            >
              <ChevronRight
                size={12}
                className={`transition-transform ${expanded ? 'rotate-90' : ''}`}
                aria-hidden="true"
              />
              {expanded ? 'Hide math' : 'Show math'}
            </button>
          )}
          {hasBreakdown && expanded && (
            <div id={bodyId}>
              <BreakdownStrip breakdown={breakdown} />
            </div>
          )}
        </div>
      </div>
    </ParchmentCard>
  );
}

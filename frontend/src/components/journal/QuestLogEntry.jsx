import { Check } from 'lucide-react';
import RuneBadge from './RuneBadge';

/**
 * QuestLogEntry — a single checkable row for today's to-dos, chores,
 * homework, milestone steps, trial targets, and habit taps. Designed as
 * the unified journal entry across the whole app.
 *
 * Props:
 *   title     : string (required)
 *   meta      : string | node — small secondary line (date, project, type)
 *   reward    : string | node — e.g. "$1.50 • 5🪙" or "+25 XP"
 *   status    : "pending" | "done" | "locked" | "overdue"
 *   onAction  : () => void — primary click handler (check-off or open)
 *   actionLabel : string — optional label for the primary action button
 *   icon      : node — optional leading icon/glyph
 *   tone      : RuneBadge tone for the kind-tag
 *   kind      : string — label shown in the kind-tag (e.g. "Ritual", "Venture")
 */
export default function QuestLogEntry({
  title,
  meta,
  reward,
  status = 'pending',
  onAction,
  actionLabel,
  icon,
  kind,
  tone = 'teal',
  className = '',
}) {
  const done = status === 'done';
  const locked = status === 'locked';
  const overdue = status === 'overdue';

  return (
    <li
      className={`group relative flex items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors
        ${done
          ? 'bg-moss/10 border-moss/30 text-ink-secondary'
          : overdue
          ? 'bg-ember/10 border-ember/40'
          : locked
          ? 'bg-ink-page-shadow/30 border-ink-page-shadow/50 text-ink-whisper'
          : 'bg-ink-page border-ink-page-shadow hover:border-sheikah-teal/60'
        } ${className}`}
    >
      {/* Leading check-glyph */}
      <button
        type="button"
        onClick={!locked ? onAction : undefined}
        disabled={locked}
        aria-label={done ? 'Completed' : actionLabel || `Complete ${title}`}
        className={`flex-shrink-0 w-7 h-7 rounded-full border flex items-center justify-center transition-all
          ${done
            ? 'bg-moss border-moss text-ink-page-rune-glow'
            : overdue
            ? 'border-ember/70 hover:bg-ember/20'
            : locked
            ? 'border-ink-page-shadow cursor-not-allowed'
            : 'border-sheikah-teal/60 hover:bg-sheikah-teal/15 hover:border-sheikah-teal'
          }`}
      >
        {done ? <Check size={14} strokeWidth={3} /> : null}
      </button>

      {/* Body */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {icon ? <span className="flex-shrink-0 text-ink-secondary">{icon}</span> : null}
          <span
            className={`font-body font-semibold text-sm truncate ${done ? 'line-through opacity-70' : ''}`}
          >
            {title}
          </span>
          {kind ? (
            <RuneBadge tone={tone} size="sm">
              {kind}
            </RuneBadge>
          ) : null}
        </div>
        {meta ? (
          <div className="text-xs font-script text-ink-whisper mt-0.5 truncate">
            {meta}
          </div>
        ) : null}
      </div>

      {/* Reward tag */}
      {reward ? (
        <div className="flex-shrink-0 font-rune text-xs text-ember-deep pl-2">
          {reward}
        </div>
      ) : null}
    </li>
  );
}

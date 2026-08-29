import { useState, useCallback } from 'react';
import { Check, Loader2 } from 'lucide-react';
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
 *   onAction  : () => void — primary click handler (check-off or open).
 *               If it returns a Promise, the row shows a processing state.
 *   actionLabel : string — optional label for the primary action button
 *   icon      : node — optional leading icon/glyph
 *   tone      : RuneBadge tone for the kind-tag
 *   kind      : string — label shown in the kind-tag (e.g. "Duty", "Shift")
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
  const [processing, setProcessing] = useState(false);
  const handleAction = useCallback(() => {
    if (!onAction || processing) return;
    const result = onAction();
    if (result && typeof result.then === 'function') {
      setProcessing(true);
      result.finally(() => setProcessing(false));
    }
  }, [onAction, processing]);

  const done = status === 'done';
  const locked = status === 'locked';
  const overdue = status === 'overdue';

  return (
    <li
      className={`group relative rounded-xl border transition-colors
        ${processing
          ? 'bg-sheikah-teal/5 border-sheikah-teal/40 opacity-75'
          : done
          ? 'bg-moss/10 border-moss/30 text-ink-secondary'
          : overdue
          ? 'bg-ember/10 border-ember/40'
          : locked
          ? 'bg-ink-page-shadow/30 border-ink-page-shadow/50 text-ink-whisper'
          : 'bg-ink-page border-ink-page-shadow hover:border-sheikah-teal/60'
        } ${className}`}
    >
      {/*
        The whole row is the button. The 28px check-glyph used to be the only
        hit area on the most-tapped control in the kids' daily loop — a tap on
        the title (the obvious target) did nothing. Wrapping the row keeps a
        single control per row, so the accessible name stays "Complete {title}"
        and the row clears the app's 44px tap floor on its own height.
      */}
      <button
        type="button"
        onClick={!locked && !processing ? handleAction : undefined}
        disabled={locked || processing}
        aria-label={done ? 'Completed' : processing ? `Processing ${title}` : actionLabel || `Complete ${title}`}
        className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left min-h-11 disabled:cursor-not-allowed"
      >
        {/* Leading check-glyph — decorative now that the row carries the label. */}
        <span
          aria-hidden="true"
          className={`flex-shrink-0 w-7 h-7 rounded-full border flex items-center justify-center transition-all
            ${done
              ? 'bg-moss border-moss text-ink-page-rune-glow'
              : processing
              ? 'border-sheikah-teal animate-pulse'
              : overdue
              ? 'border-ember/70 group-hover:bg-ember/20'
              : locked
              ? 'border-ink-page-shadow'
              : 'border-sheikah-teal/60 group-hover:bg-sheikah-teal/15 group-hover:border-sheikah-teal'
            }`}
        >
          {done ? <Check size={14} strokeWidth={3} /> : processing ? <Loader2 size={14} className="animate-spin text-sheikah-teal-deep" /> : null}
        </span>

        {/* Body */}
        <span className="flex-1 min-w-0 block">
          <span className="flex items-center gap-2 flex-wrap">
            {icon ? <span className="flex-shrink-0 text-ink-secondary">{icon}</span> : null}
            <span
              className={`font-body font-semibold text-body truncate ${done ? 'line-through opacity-70' : ''}`}
            >
              {title}
            </span>
            {kind ? (
              <RuneBadge tone={tone} size="sm">
                {kind}
              </RuneBadge>
            ) : null}
          </span>
          {meta ? (
            <span className="text-caption font-script text-ink-whisper mt-0.5 truncate block">
              {meta}
            </span>
          ) : null}
        </span>

        {/* Reward tag */}
        {reward ? (
          <span className="flex-shrink-0 font-rune text-caption text-ember-deep pl-2">
            {reward}
          </span>
        ) : null}
      </button>
    </li>
  );
}

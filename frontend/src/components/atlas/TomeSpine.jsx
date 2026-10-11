import { forwardRef } from 'react';
import { Check } from 'lucide-react';
import { PROGRESS_TIER } from './mastery.constants';

/** A readable collection card or compact filter pill, retaining the descriptor API. */
const TomeSpine = forwardRef(function TomeSpine(
  {
    id,
    name,
    icon,
    chip = null,
    progressPct = null,
    tier = PROGRESS_TIER.locked,
    active = false,
    ariaLabel,
    variant = 'codex',
    compact = variant === 'vessel',
    tabIndex = active ? 0 : -1,
    onClick,
    onKeyDown,
  },
  ref,
) {
  const tierKey =
    Object.keys(PROGRESS_TIER).find((key) => PROGRESS_TIER[key] === tier) || 'locked';
  const progress = Number.isFinite(progressPct) ? Math.max(0, Math.min(100, progressPct)) : null;
  const hasChip = chip != null && chip !== '';
  const label = ariaLabel || [name, hasChip ? chip : null, progress != null ? `${Math.round(progress)}% progress` : null]
    .filter((part) => part != null)
    .join(', ');

  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active}
      aria-label={label}
      tabIndex={tabIndex}
      onClick={onClick}
      onKeyDown={onKeyDown}
      data-spine-id={id}
      data-spine-variant={variant}
      data-active={active ? 'true' : 'false'}
      data-tier={tierKey}
      className={`min-w-0 max-w-full min-h-11 scroll-m-1 border-2 text-ink-primary font-body transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep focus-visible:ring-offset-2 focus-visible:ring-offset-ink-page ${
        compact
          ? 'rounded-full flex items-center gap-2 px-3 py-2 text-body'
          : 'rounded-3xl flex flex-col items-start gap-3 p-3 text-left shadow-sm'
      } ${
        active
          ? 'border-sheikah-teal-deep bg-sheikah-teal/15'
          : 'border-ink-page-shadow bg-ink-page-rune-glow hover:border-sheikah-teal-deep/60 hover:bg-ink-page-aged'
      }`}
    >
      {compact ? (
        <>
          {icon && <span aria-hidden="true" className="shrink-0 text-base leading-none">{icon}</span>}
          <span className="min-w-0 break-words font-semibold">{name}</span>
          {hasChip && (
            <span className="shrink-0 rounded-full bg-ink-page-aged px-2 py-0.5 text-caption font-semibold tabular-nums">
              {chip}
            </span>
          )}
          {/* Reserve the selection marker so choosing a pill never reflows it. */}
          <Check
            size={16}
            aria-hidden="true"
            data-current-marker="true"
            className={`shrink-0 text-sheikah-teal-deep ${active ? '' : 'invisible'}`}
          />
        </>
      ) : (
        <>
          <span className="flex flex-wrap items-center justify-between gap-2 w-full">
            <span aria-hidden="true" className="inline-flex items-center justify-center w-9 h-9 rounded-2xl bg-ink-page-aged text-xl shrink-0">
              {icon || '✦'}
            </span>
            {/* Keep the marker's geometry stable before keyboard reveal. */}
            <span
              aria-hidden="true"
              data-current-marker="true"
              className={`inline-flex items-center gap-1 text-tiny font-semibold text-sheikah-teal-deep ${active ? '' : 'invisible'}`}
            >
              <Check size={16} />
              <span className="hidden sm:inline">Current</span>
            </span>
          </span>
          <span className="w-full break-words font-semibold text-body leading-snug flex-1">{name}</span>
          {(hasChip || progress != null) && (
            <span className="flex flex-wrap items-center justify-between gap-2 w-full">
              {hasChip && (
                <span className="rounded-full bg-ink-page-aged px-2 py-0.5 text-caption font-semibold tabular-nums">
                  {chip}
                </span>
              )}
              {progress != null && (
                <span className={`text-caption tabular-nums ${PROGRESS_TIER[tierKey].chip}`}>
                  {Math.round(progress)}%
                </span>
              )}
            </span>
          )}
        </>
      )}
      {progress != null && (
        <span
          role="progressbar"
          aria-label={`${name} progress`}
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          data-collection-progress="true"
          data-progress={progress}
          data-tier={tierKey}
          className={compact ? `shrink-0 text-caption tabular-nums ${PROGRESS_TIER[tierKey].chip}` : 'h-1.5 w-full rounded-full overflow-hidden bg-ink-page-shadow/40'}
        >
          {compact ? `${Math.round(progress)}%` : (
            <span
              className={`block h-full rounded-full ${PROGRESS_TIER[tierKey].bar} motion-safe:transition-[width] motion-safe:duration-500`}
              style={{ width: `${progress}%` }}
            />
          )}
        </span>
      )}
    </button>
  );
});

export default TomeSpine;

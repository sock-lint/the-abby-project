import { forwardRef } from 'react';
import { PROGRESS_TIER } from './mastery.constants';

// Existing tier and data hooks remain shared with the catalog pages. The
// collection tile gives every label a horizontal reading direction on phones.
const TIER_ACCENT = {
  locked: 'var(--color-ink-page-shadow)',
  nascent: 'var(--color-moss)',
  rising: 'var(--color-sheikah-teal-deep)',
  cresting: 'var(--color-ember)',
  gilded: 'var(--color-gold-leaf)',
};

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
    onClick,
    onKeyDown,
  },
  ref,
) {
  const tierKey =
    Object.keys(PROGRESS_TIER).find((key) => PROGRESS_TIER[key] === tier) || 'locked';
  const isCodex = variant === 'codex';
  const accent = TIER_ACCENT[tierKey];
  const surface = active ? 'var(--color-ink-page-aged)' : 'var(--color-ink-page-rune-glow)';

  return (
    <button
      ref={ref}
      type="button"
      role="tab"
      aria-selected={active ? 'true' : 'false'}
      aria-label={ariaLabel || name}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      onKeyDown={onKeyDown}
      data-spine-id={id}
      data-spine-variant={variant}
      data-active={active ? 'true' : 'false'}
      data-binding={isCodex ? 'leather' : 'drawer'}
      data-tier={tierKey}
      style={isCodex ? { '--spine-tint': surface } : undefined}
      className={`snap-start shrink-0 relative rounded-3xl border-2 flex flex-col items-center w-36 min-h-40 p-3 gap-2 overflow-hidden text-ink-primary shadow-sm transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep focus-visible:ring-offset-2 focus-visible:ring-offset-ink-page ${
        isCodex ? 'spine-leather' : 'bg-ink-page-rune-glow'
      } ${
        active
          ? 'border-sheikah-teal-deep bg-ink-page-aged'
          : 'border-ink-page-shadow hover:border-sheikah-teal-deep/60'
      }`}
    >
      {isCodex && (
        <>
          <span
            aria-hidden="true"
            data-spine-headband="true"
            data-tier={tierKey}
            className="absolute top-0 inset-x-4 h-1 rounded-full opacity-25 pointer-events-none"
            style={{ backgroundColor: accent }}
          />
          {/* Preserve legacy ornament selectors for existing catalog consumers. */}
          <span aria-hidden="true" data-spine-band="head" className="hidden" />
          <span aria-hidden="true" data-spine-band="middle" className="hidden" />
          <span aria-hidden="true" data-spine-band="foot" className="hidden" />
          <span aria-hidden="true" data-spine-edge="true" className="hidden" />
        </>
      )}

      {isCodex ? (
        <>
          <span
            aria-hidden="true"
            data-spine-medallion="true"
            className="inline-flex items-center justify-center w-10 h-10 rounded-2xl bg-ink-page-aged text-2xl shrink-0"
          >
            {icon || '✦'}
          </span>
          <span
            aria-hidden="true"
            data-spine-title="true"
            className="spine-foil spine-foil-glint font-display font-bold text-body leading-snug text-center flex-1 min-h-0 w-full break-words"
          >
            {name}
          </span>
        </>
      ) : (
        <>
          <span
            aria-hidden="true"
            data-vessel-pull="true"
            className={`absolute top-0 inset-x-4 h-1 rounded-full ${active ? 'bg-sheikah-teal-deep/25' : 'bg-ink-page-shadow/40'}`}
          />
          <span aria-hidden="true" className="inline-flex items-center justify-center w-10 h-10 rounded-2xl bg-ink-page-aged text-2xl shrink-0">
            {icon || '✦'}
          </span>
          <span aria-hidden="true" className="font-display font-bold text-body leading-snug text-center flex-1 min-h-0 w-full break-words">
            {name}
          </span>
        </>
      )}

      <span className="flex flex-col items-center gap-2 w-full shrink-0">
        {chip != null && chip !== '' && (
          <span className="font-body font-bold text-tiny bg-ink-page-aged text-ink-primary px-2 py-0.5 rounded-full tabular-nums">
            {chip}
          </span>
        )}
        {progressPct != null ? (
          <span
            aria-hidden="true"
            data-tome-band="true"
            data-tier={tierKey}
            className="relative h-1.5 w-full rounded-full overflow-hidden bg-ink-page-shadow/40"
          >
            <span
              className={`absolute inset-y-0 left-0 rounded-full ${tier.bar} motion-safe:transition-[width] motion-safe:duration-500`}
              style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
            />
          </span>
        ) : (
          <span aria-hidden="true" data-tome-band="true" data-tier={tierKey} className="h-px w-full bg-ink-page-shadow/40 rounded-full" />
        )}
      </span>

      {isCodex && (
        <span
          aria-hidden="true"
          data-tome-ribbon="true"
          className={`absolute top-2 right-2 w-1.5 h-3 rounded-full bg-sheikah-teal-deep origin-top motion-safe:transition-transform motion-safe:duration-300 ${active ? 'scale-y-100 animate-ribbon-settle' : 'scale-y-0'}`}
        />
      )}
    </button>
  );
});

export default TomeSpine;

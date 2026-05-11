import { forwardRef } from 'react';
import { PROGRESS_TIER } from './mastery.constants';

/**
 * TomeSpine — a bound tome on a shelf. One per item.
 *
 * Two variants today, same outer dimensions so any mix can sit on the same
 * TomeShelf without breaking the snap-rail layout:
 *
 *   - `codex` (default) — vertical-text book spine. Best for narrative or
 *     chapter content: skills, badges, cosmetics, yearbook years, journal.
 *     Reads as "a book of pages."
 *   - `vessel` — horizontal label, icon-forward, count-chip prominent.
 *     Best for "collections of things": inventory compartments (eggs,
 *     potions, …), sketchbook filter pills (projects, homework, …).
 *     Reads as "a labeled drawer / apothecary jar."
 *
 * Domain-agnostic: pass flat props for whatever the consumer wants to show.
 * The active spine lifts, tilts, and unfurls a bookmark ribbon regardless
 * of variant. Lives inside a role="tablist" parent (TomeShelf) — same
 * keyboard contract (ArrowRight/Left) and same aria-selected semantics
 * as any tab.
 *
 * When `progressPct == null` the foot band becomes a thin static hairline
 * (used by surfaces like Inventory or Yearbook where "progress" isn't a
 * meaningful concept — a satchel drawer or a calendar year aren't
 * collections to fill).
 */
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
  const activeCls = active
    ? 'bg-ink-page-rune-glow border-gold-leaf shadow-[0_6px_18px_-6px_rgba(45,31,21,0.45)] -translate-y-1 -rotate-1'
    : 'bg-ink-page-aged border-ink-page-shadow hover:border-sheikah-teal/60 hover:bg-ink-page-rune-glow';

  const tierKey = Object.keys(PROGRESS_TIER).find((k) => PROGRESS_TIER[k] === tier) || 'locked';

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
      className={`snap-start shrink-0 relative rounded-md border-2 transition-all duration-200 flex flex-col items-center w-[68px] h-[180px] md:w-[76px] md:h-[200px] py-3 px-1 overflow-hidden ${activeCls}`}
    >
      {variant === 'vessel' ? (
        <VesselBody name={name} icon={icon} active={active} />
      ) : (
        <CodexBody name={name} icon={icon} active={active} />
      )}

      {/* Bottom group — chip above the foot band. Living inside the flex
          tree (not absolute-positioned) means the body above can never
          collide with the chip no matter how long the title or how big
          the vessel icon. The flex-1 body shrinks the available middle
          space; this group sits naturally below it. */}
      <span className="flex flex-col items-center gap-1.5 w-full shrink-0 mt-1.5">
        {chip != null && chip !== '' && (
          <span
            className={`font-rune uppercase tracking-wider px-1.5 py-0.5 rounded tabular-nums ${
              variant === 'vessel' ? 'text-tiny font-bold' : 'text-micro'
            } ${
              active ? 'bg-gold-leaf/20 text-ember-deep' : 'bg-ink-page-shadow/40 text-ink-whisper'
            }`}
          >
            {chip}
          </span>
        )}
        {progressPct != null ? (
          <span
            aria-hidden="true"
            data-tome-band="true"
            data-tier={tierKey}
            className="relative h-1.5 w-[calc(100%-8px)] rounded-full overflow-hidden bg-ink-page-shadow/55 border border-ink-page-shadow/40"
          >
            <span
              className={`absolute inset-y-0 left-0 rounded-full ${tier.bar}`}
              style={{
                width: `${Math.max(0, Math.min(100, progressPct))}%`,
                transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            />
          </span>
        ) : (
          <span
            aria-hidden="true"
            data-tome-band="true"
            data-tier={tierKey}
            className="h-px w-[calc(100%-8px)] bg-ink-page-shadow/40 rounded-full"
          />
        )}
      </span>

      {/* Bookmark ribbon — draped from the head cap only on the active spine.
          Shared across variants so the active-state vocabulary stays
          consistent across the shelf. Animates scale-y 0 → 1 via Tailwind's
          transition-transform because the parent already re-renders on
          activeId change. */}
      <span
        aria-hidden="true"
        data-tome-ribbon="true"
        className={`absolute top-0 right-3 w-2 bg-sheikah-teal-deep origin-top transition-transform duration-300 ease-out ${
          active ? 'scale-y-100' : 'scale-y-0'
        }`}
        style={{
          height: '38px',
          clipPath: 'polygon(0 0, 100% 0, 100% 100%, 50% 78%, 0 100%)',
        }}
      />
    </button>
  );
});

/**
 * Codex body — small icon at the head cap, vertical display-serif title
 * filling the middle. The original "book spine" layout.
 */
function CodexBody({ name, icon, active }) {
  return (
    <>
      {/* Head cap — icon medallion. */}
      <span
        aria-hidden="true"
        className={`text-2xl md:text-3xl leading-none drop-shadow-[0_1px_0_var(--color-ink-page-rune-glow)] ${
          active ? '' : 'opacity-85'
        }`}
      >
        {icon || '✦'}
      </span>

      {/* Vertical spine title. writing-mode CSS + text-orientation keep the
          letters upright reading bottom-to-top, mimicking a printed spine. */}
      <span
        aria-hidden="true"
        className={`font-display italic font-semibold leading-tight text-center px-0.5 flex items-center justify-center flex-1 min-h-0 ${
          active ? 'text-ink-primary' : 'text-ink-secondary'
        }`}
        style={{
          writingMode: 'vertical-rl',
          textOrientation: 'mixed',
          transform: 'rotate(180deg)',
          fontSize: '14px',
          letterSpacing: '0.02em',
          lineHeight: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {name}
      </span>
    </>
  );
}

/**
 * Vessel body — drawer-pull hint at the head, large centered icon, then a
 * horizontal title. Reads as a labeled drawer or apothecary jar. Title can
 * wrap onto two lines (line-clamp-2) so labels like "Avatar Frames" /
 * "Pet Accessories" stay legible without ellipsis.
 */
function VesselBody({ name, icon, active }) {
  return (
    <>
      {/* Drawer-pull — a small horizontal nub at the top, mimicking a
          chest-of-drawers handle. Tints gold-leaf when active. */}
      <span
        aria-hidden="true"
        data-vessel-pull="true"
        className={`h-1 w-6 rounded-full ${
          active ? 'bg-gold-leaf' : 'bg-ink-page-shadow/60'
        }`}
      />

      {/* Centered icon — larger than the codex head cap, occupies the
          middle of the drawer face. flex-1 keeps it vertically centered
          regardless of how tall the label below ends up. */}
      <span
        aria-hidden="true"
        className={`flex items-center justify-center flex-1 min-h-0 text-3xl md:text-4xl leading-none drop-shadow-[0_1px_0_var(--color-ink-page-rune-glow)] ${
          active ? '' : 'opacity-85'
        }`}
      >
        {icon || '✦'}
      </span>

      {/* Horizontal label. Two-line clamp so multi-word labels don't get
          ellipsis-cut at 76px wide. */}
      <span
        aria-hidden="true"
        className={`font-display italic font-semibold leading-tight text-center px-0.5 shrink-0 ${
          active ? 'text-ink-primary' : 'text-ink-secondary'
        }`}
        style={{
          fontSize: '11px',
          letterSpacing: '0.01em',
          lineHeight: 1.15,
          display: '-webkit-box',
          WebkitLineClamp: 2,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}
      >
        {name}
      </span>
    </>
  );
}

export default TomeSpine;

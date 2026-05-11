import { forwardRef } from 'react';
import { PROGRESS_TIER } from './mastery.constants';

/**
 * TomeSpine — a bound tome on a shelf. One per item.
 *
 * Two variants today, same outer dimensions so any mix can sit on the same
 * TomeShelf without breaking the snap-rail layout:
 *
 *   - `codex` (default) — a hand-bound library tome. Tooled-leather panel
 *     tinted by progress tier, three raised binding bands, brass medallion
 *     head cap, woven headband, foil-stamp vertical title, gilt page-edge.
 *     Reads as "a book pulled from a library shelf." This is THE book
 *     vocabulary in the app — fans out to Skills, Badges, Yearbook,
 *     cosmetic chapters, and JournalReader.
 *   - `vessel` — horizontal label, icon-forward, count-chip prominent.
 *     Best for "collections of things": inventory compartments (eggs,
 *     potions, …), sketchbook filter pills (projects, homework, …).
 *     Reads as "a labeled drawer / apothecary jar."
 *
 * Domain-agnostic: pass flat props for whatever the consumer wants to show.
 * The active spine lifts, tilts (rotateY revealing a page-block sliver),
 * and unfurls a bookmark ribbon regardless of variant. Lives inside a
 * role="tablist" parent (TomeShelf) — same keyboard contract
 * (ArrowRight/Left) and same aria-selected semantics as any tab.
 *
 * When `progressPct == null` the foot band becomes a thin static hairline
 * (used by surfaces like Inventory or Yearbook where "progress" isn't a
 * meaningful concept — a satchel drawer or a calendar year aren't
 * collections to fill).
 */

// Tier → binding palette. Locked tomes look pristine and cool (untouched on
// the shelf); gilded tomes look warm and burnished. All five tones reuse
// the leather/headband tokens declared in index.css so journal-cover swaps
// (hyrule / vigil / sunlit / …) drive the look from one place.
const TIER_LEATHER = {
  locked: {
    spineTint: 'var(--color-leather-locked)',
    headband: 'var(--color-headband-locked)',
    foilTop: 'var(--color-ink-whisper)',
    foilBottom: 'var(--color-ink-page-shadow)',
    edgeOpacity: 0.35,
    discBg: 'var(--color-ink-page-shadow)',
    discDim: true,
  },
  nascent: {
    spineTint: 'var(--color-leather-nascent)',
    headband: 'var(--color-headband-nascent)',
    foilTop: 'var(--color-gold-leaf)',
    foilBottom: 'var(--color-ember-deep)',
    edgeOpacity: 0.62,
    discBg: 'var(--color-gold-leaf)',
    discDim: false,
  },
  rising: {
    spineTint: 'var(--color-leather-rising)',
    headband: 'var(--color-headband-rising)',
    foilTop: 'var(--color-gold-leaf)',
    foilBottom: 'var(--color-ember-deep)',
    edgeOpacity: 0.75,
    discBg: 'var(--color-gold-leaf)',
    discDim: false,
  },
  cresting: {
    spineTint: 'var(--color-leather-cresting)',
    headband: 'var(--color-headband-cresting)',
    foilTop: 'var(--color-gold-leaf)',
    foilBottom: 'var(--color-ember-deep)',
    edgeOpacity: 0.88,
    discBg: 'var(--color-gold-leaf)',
    discDim: false,
  },
  gilded: {
    spineTint: 'var(--color-leather-gilded)',
    headband: 'var(--color-headband-gilded)',
    foilTop: 'var(--color-gold-leaf)',
    foilBottom: 'var(--color-gold-leaf)',
    edgeOpacity: 1,
    discBg: 'var(--color-gold-leaf)',
    discDim: false,
  },
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
    Object.keys(PROGRESS_TIER).find((k) => PROGRESS_TIER[k] === tier) || 'locked';
  const isCodex = variant === 'codex';
  const leather = TIER_LEATHER[tierKey] || TIER_LEATHER.locked;

  // Active vs idle button shell. Codex variants get the pull-from-shelf
  // hover + open-binding tilt; vessels keep their flat drawer behavior.
  let buttonCls;
  if (isCodex) {
    buttonCls = active
      ? 'border-gold-leaf shadow-[0_12px_26px_-8px_rgba(45,31,21,0.55)] [transform:translateY(-6px)_rotate(-1.2deg)_rotateY(-7deg)]'
      : 'border-ink-page-shadow hover:border-sheikah-teal/60 hover:[transform:translateY(-4px)_scale(1.03)] hover:shadow-[0_14px_24px_-6px_rgba(45,31,21,0.45)]';
  } else {
    buttonCls = active
      ? 'bg-ink-page-rune-glow border-gold-leaf shadow-[0_6px_18px_-6px_rgba(45,31,21,0.45)] -translate-y-1 -rotate-1'
      : 'bg-ink-page-aged border-ink-page-shadow hover:border-sheikah-teal/60 hover:bg-ink-page-rune-glow';
  }

  const surfaceCls = isCodex ? 'spine-leather' : '';

  // CSS custom property feeds .spine-leather's background-color. Only set
  // on codex spines — vessels keep their bg-ink-page-* utility classes.
  const style = isCodex ? { '--spine-tint': leather.spineTint } : undefined;

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
      style={style}
      className={`snap-start shrink-0 relative rounded-md border-2 transition-all duration-200 flex flex-col items-center w-[68px] h-[180px] md:w-[76px] md:h-[200px] py-3 px-1 overflow-hidden will-change-transform ${surfaceCls} ${buttonCls}`}
    >
      {isCodex && <SpineDressings tierKey={tierKey} leather={leather} active={active} />}

      {variant === 'vessel' ? (
        <VesselBody name={name} icon={icon} active={active} />
      ) : (
        <CodexBody name={name} icon={icon} active={active} leather={leather} />
      )}

      {/* Bottom group — chip above the foot band. Living inside the flex
          tree (not absolute-positioned) means the body above can never
          collide with the chip no matter how long the title or how big
          the vessel icon. The flex-1 body shrinks the available middle
          space; this group sits naturally below it. */}
      <span className="relative z-10 flex flex-col items-center gap-1.5 w-full shrink-0 mt-1.5">
        {chip != null && chip !== '' && (
          <span
            className={`font-rune uppercase tracking-wider px-1.5 py-0.5 rounded tabular-nums ${
              variant === 'vessel' ? 'text-tiny font-bold' : 'text-micro'
            } ${
              active ? 'bg-gold-leaf/30 text-ember-deep' : 'bg-ink-page-shadow/40 text-ink-whisper'
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
          consistent across the shelf. Codex variants get an extra settle
          curl (animate-ribbon-settle) so the ribbon reads as fabric falling
          into place; vessels keep the original scale-y tween. The
          scale-y-0/100 classes are preserved (tests pin against them). */}
      <span
        aria-hidden="true"
        data-tome-ribbon="true"
        className={`absolute top-0 right-3 w-2 bg-sheikah-teal-deep origin-top transition-transform duration-300 ease-out z-20 ${
          active ? `scale-y-100 ${isCodex ? 'animate-ribbon-settle' : ''}` : 'scale-y-0'
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
 * SpineDressings — absolute-positioned decorative layers on a codex spine:
 * cloth headband across the top, three raised binding bands, gilt
 * page-edge down the right, and a cream page-block sliver visible only
 * when active (revealed by the rotateY tilt). All aria-hidden; none of
 * these are queried by tests except via `data-*` selectors.
 */
function SpineDressings({ tierKey, leather, active }) {
  const bindingBandShadow =
    'inset 0 -1px 0 rgba(45, 31, 21, 0.42), 0 1px 0 rgba(255, 248, 224, 0.30)';

  return (
    <>
      {/* Cloth headband — the woven cap at the top of a real hardback.
          Tier-tinted so a row of tomes flashes its progress vocabulary
          across the shelf even when the leather itself is muted. */}
      <span
        aria-hidden="true"
        data-spine-headband="true"
        data-tier={tierKey}
        className="absolute top-0 left-0 right-0 h-1.5 pointer-events-none"
        style={{
          backgroundColor: leather.headband,
          opacity: leather.edgeOpacity,
          boxShadow:
            'inset 0 -1px 0 rgba(45, 31, 21, 0.35), inset 0 1px 0 rgba(255, 248, 224, 0.25)',
        }}
      />

      {/* Three raised binding bands — short horizontal ridges across the
          spine that bookbinders sew over the cord. Largest "real book"
          tell after the leather grain. */}
      <span
        aria-hidden="true"
        data-spine-band="head"
        className="absolute left-0 right-0 h-[2px] pointer-events-none"
        style={{ top: '22%', boxShadow: bindingBandShadow }}
      />
      <span
        aria-hidden="true"
        data-spine-band="middle"
        className="absolute left-0 right-0 h-[2px] pointer-events-none"
        style={{ top: '52%', boxShadow: bindingBandShadow }}
      />
      <span
        aria-hidden="true"
        data-spine-band="foot"
        className="absolute left-0 right-0 h-[2px] pointer-events-none"
        style={{ top: '82%', boxShadow: bindingBandShadow }}
      />

      {/* Gilt page-edge — the page block's gilded edge peeks down the
          right side of the spine. Brighter at higher progress tiers via
          edgeOpacity. */}
      <span
        aria-hidden="true"
        data-spine-edge="true"
        className="absolute top-0 bottom-0 right-0 w-[2px] pointer-events-none"
        style={{
          backgroundImage:
            'linear-gradient(180deg, var(--color-gold-leaf) 0%, var(--color-ember-deep) 50%, var(--color-gold-leaf) 100%)',
          opacity: leather.edgeOpacity,
        }}
      />

      {/* Active page-block sliver — the cream-striated cut of pages
          revealed by the rotateY tilt when this spine is selected. */}
      {active && (
        <span
          aria-hidden="true"
          data-spine-pageblock="true"
          className="page-block absolute top-2 bottom-2 right-[3px] w-1.5 pointer-events-none rounded-[1px]"
          style={{
            boxShadow:
              'inset 1px 0 0 rgba(45, 31, 21, 0.35), inset -1px 0 0 rgba(45, 31, 21, 0.20)',
          }}
        />
      )}
    </>
  );
}

/**
 * Codex body — brass medallion at the head cap, vertical foil-stamped
 * display-serif title filling the middle. The original "book spine"
 * layout, now dressed.
 */
function CodexBody({ name, icon, active, leather }) {
  return (
    <>
      {/* Brass medallion — bevelled disc holding the icon. Disc dims for
          locked tomes so a fresh shelf reads as "not yet pulled down."
          Three-layer box-shadow simulates the inner highlight + ring
          shadow + outer drop you'd see on a real brass cabochon. */}
      <span
        aria-hidden="true"
        data-spine-medallion="true"
        className={`relative z-10 inline-flex items-center justify-center w-7 h-7 md:w-8 md:h-8 rounded-full mt-1 ${
          active ? '' : 'opacity-95'
        }`}
        style={{
          backgroundColor: leather.discBg,
          boxShadow:
            'inset 0 1px 0 rgba(255, 248, 224, 0.65), inset 0 -1px 0 rgba(45, 31, 21, 0.45), 0 0 0 1px rgba(143, 62, 29, 0.45), 0 2px 4px rgba(45, 31, 21, 0.40)',
        }}
      >
        <span
          className={`text-base md:text-lg leading-none ${
            leather.discDim ? 'opacity-70' : ''
          }`}
          style={{
            filter: leather.discDim ? 'grayscale(40%)' : 'none',
            textShadow: '0 1px 0 rgba(255, 248, 224, 0.55)',
          }}
        >
          {icon || '✦'}
        </span>
      </span>

      {/* Vertical spine title — foil-stamped via .spine-foil (background-clip
          gradient) with the .spine-foil-glint sheen sweep on hover/active.
          writing-mode + text-orientation + rotate(180deg) keep the letters
          upright reading bottom-to-top, mimicking a printed spine. */}
      <span
        aria-hidden="true"
        data-spine-title="true"
        className="spine-foil spine-foil-glint font-display italic font-bold leading-tight text-center px-0.5 flex items-center justify-center flex-1 min-h-0 relative z-10"
        style={{
          writingMode: 'vertical-rl',
          textOrientation: 'mixed',
          transform: 'rotate(180deg)',
          fontSize: '14px',
          letterSpacing: '0.05em',
          lineHeight: 1,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          '--foil-tone-top': leather.foilTop,
          '--foil-tone-bottom': leather.foilBottom,
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

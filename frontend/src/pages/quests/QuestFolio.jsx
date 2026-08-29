import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import FolioHeadband from '../../components/atlas/FolioHeadband';
import RarityStrand from '../../components/atlas/RarityStrand';
import { tierForProgress } from '../../components/atlas/mastery.constants';

/**
 * QuestFolio — the verso/recto shell shared by Ventures, Duties, Study,
 * Rituals, and Movement. Modelled on pages/achievements/FolioSpread.jsx
 * but parameterised so a tab can fill in its own letter / title / stats /
 * progress without dragging the skill-tree XP math along.
 *
 * Verso (left, ~220-260px desktop · top banner mobile): cloth headband
 *   tied to tier (components/atlas/FolioHeadband), brass-rimmed
 *   illuminated drop-cap, script kicker, display-serif title with
 *   foil-glint, stats row, progress bar, optional rarity strand.
 *
 * Recto (right): consumer-supplied children — the working list.
 *
 * No new tier ladders, halo colors, or keyframes — composition against
 * the existing Atlas cohort (per components/README.md guidance).
 */

// Bottom stop of the title's foil gradient, tier-tinted so the folio's
// heading matches the spine it opens from. The headband's own tier tint
// lives in components/atlas/FolioHeadband.
const FOIL_BOTTOM = {
  locked: 'var(--color-ink-page-shadow)',
  nascent: 'var(--color-ember-deep)',
  rising: 'var(--color-ember-deep)',
  cresting: 'var(--color-ember-deep)',
  gilded: 'var(--color-gold-leaf)',
};

function tierKeyOf(tier) {
  if (tier.bar?.includes('gold-leaf')) return 'gilded';
  if (tier.bar?.includes('ember')) return 'cresting';
  if (tier.bar?.includes('sheikah')) return 'rising';
  if (tier.bar?.includes('moss')) return 'nascent';
  return 'locked';
}

export default function QuestFolio({
  letter,
  title,
  kicker,
  meta,
  stats = [],
  progressPct = 0,
  progressLabel,
  rarityCounts,
  children,
  className = '',
}) {
  const safePct = Math.max(0, Math.min(100, Number(progressPct) || 0));
  const tier = tierForProgress({ unlocked: safePct > 0, progressPct: safePct, level: 0 });
  const tierKey = tierKeyOf(tier);
  const foilBottom = FOIL_BOTTOM[tierKey] ?? FOIL_BOTTOM.rising;
  const safeStats = (stats ?? []).slice(0, 3);
  const firstLetter = (letter || title || '✦').toString().trim().charAt(0).toUpperCase() || '✦';
  // Phone-only condensed incipit: the same stats the full plate renders,
  // inlined as a single caption line ("12 done · 3 waiting").
  const compactStats = safeStats.map((s) => `${s.value} ${s.label}`).join(' · ');
  const showProgress = Boolean(progressLabel) || safePct > 0;

  return (
    <ParchmentCard
      tone="bright"
      flourish
      as="section"
      aria-label={`${title} folio`}
      className={`!p-0 overflow-hidden ${className}`}
    >
      <div className="relative grid grid-cols-1 md:grid-cols-[220px_1fr] lg:grid-cols-[260px_1fr]">
        {/* Gutter — vertical fold shadow down the center on desktop. */}
        <div
          aria-hidden="true"
          className="hidden md:block absolute inset-y-4 left-[220px] lg:left-[260px] w-px bg-gradient-to-b from-transparent via-ink-page-shadow/60 to-transparent pointer-events-none"
        />

        {/* Verso — the chapter incipit. Below md it condenses to a single
            compact row (~100px) so the working list starts near the top of
            a phone screen; the full illuminated plate is untouched at md+. */}
        <aside
          data-folio-verso="true"
          data-tier={tierKey}
          data-progress={Math.round(safePct)}
          className="relative px-4 pt-4 pb-3 md:px-5 md:pt-7 md:pb-6 flex flex-col items-center text-center gap-3 border-b md:border-b-0 md:border-r border-ink-page-shadow/30"
        >
          <FolioHeadband tierKey={tierKey} />

          {/* Compact incipit — phones only. Small versal, title, inline
              stats caption, and a thin progress bar with its label. */}
          <div
            data-folio-verso-compact="true"
            data-tier={tierKey}
            data-progress={Math.round(safePct)}
            className="md:hidden flex w-full items-center gap-3 text-left"
          >
            <IlluminatedVersal
              letter={firstLetter}
              progressPct={safePct}
              tier={tier}
              size="sm"
            />
            <div className="min-w-0 flex-1">
              <h2
                className="spine-foil font-display italic text-lede leading-tight truncate"
                style={{
                  letterSpacing: '0.02em',
                  '--foil-tone-top': 'var(--color-gold-leaf)',
                  '--foil-tone-bottom': foilBottom,
                }}
              >
                {title}
              </h2>
              {compactStats && (
                <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper truncate mt-0.5">
                  {compactStats}
                </div>
              )}
              {showProgress && (
                <div className="mt-1.5">
                  <div
                    role="progressbar"
                    aria-label={`${title} progress`}
                    aria-valuenow={Math.round(safePct)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    className="relative h-1 bg-ink-page-shadow/50 rounded-full overflow-hidden"
                  >
                    <span
                      className={`absolute inset-y-0 left-0 rounded-full ${tier.bar}`}
                      style={{
                        width: `${safePct}%`,
                        transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)',
                      }}
                    />
                  </div>
                  {progressLabel && (
                    <div className="font-script text-caption text-ink-whisper truncate mt-0.5">
                      {progressLabel}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Full illuminated plate — md+ only. Markup unchanged from the
              single-variant version so desktop keeps every ornament. */}
          <div
            data-folio-verso-full="true"
            className="hidden w-full md:flex flex-col items-center text-center gap-3"
          >
          {kicker && (
            <div className="font-rune text-micro uppercase tracking-wider text-ember-deep">
              · {kicker} ·
            </div>
          )}
          {/* Brass-rimmed medallion around the versal — same head-cap
              shape FolioSpread uses on the Skills tome. */}
          <span
            aria-hidden="true"
            data-folio-medallion="true"
            className="relative inline-flex items-center justify-center rounded-full p-1"
            style={{
              backgroundImage:
                'radial-gradient(circle at 50% 30%, rgba(255,248,224,0.35) 0%, transparent 55%), linear-gradient(160deg, var(--color-gold-leaf) 0%, var(--color-ember-deep) 80%)',
              boxShadow:
                'inset 0 1px 0 rgba(255, 248, 224, 0.65), inset 0 -2px 2px rgba(45, 31, 21, 0.45), 0 0 0 1px rgba(143, 62, 29, 0.45), 0 4px 10px rgba(45, 31, 21, 0.35)',
            }}
          >
            <span
              className="rounded-full bg-ink-page p-1"
              style={{
                boxShadow:
                  'inset 0 0 0 1px rgba(45, 31, 21, 0.25), inset 0 2px 4px rgba(45, 31, 21, 0.18)',
              }}
            >
              <IlluminatedVersal
                letter={firstLetter}
                progressPct={safePct}
                tier={tier}
                size="xl"
              />
            </span>
          </span>
          <div className="space-y-0.5">
            <h2
              data-folio-title="true"
              className="spine-foil spine-foil-glint font-display italic text-xl md:text-2xl leading-tight"
              style={{
                letterSpacing: '0.02em',
                '--foil-tone-top': 'var(--color-gold-leaf)',
                '--foil-tone-bottom': foilBottom,
              }}
            >
              {title}
            </h2>
            {meta && (
              <div className="font-script text-caption text-ink-whisper">
                {meta}
              </div>
            )}
          </div>
          {safeStats.length > 0 && (
            <div className="flex items-center gap-4 pt-1">
              {safeStats.map((s, i) => (
                <span key={`${s.label}-${i}`} className="flex items-center gap-4">
                  {i > 0 && (
                    <span className="h-8 w-px bg-ink-page-shadow/40" aria-hidden="true" />
                  )}
                  <span className="text-center">
                    <span className={`block font-display italic font-bold leading-none text-2xl ${tier.chip}`}>
                      {s.value}
                    </span>
                    <span className="block text-micro font-rune uppercase tracking-wider text-ink-whisper mt-0.5">
                      {s.label}
                    </span>
                  </span>
                </span>
              ))}
            </div>
          )}
          {(progressLabel || safePct > 0) && (
            <div className="pt-2 w-full border-t border-ink-page-shadow/30">
              <div
                role="progressbar"
                aria-label={`${title} progress`}
                aria-valuenow={Math.round(safePct)}
                aria-valuemin={0}
                aria-valuemax={100}
                className="relative h-1.5 bg-ink-page-shadow/50 rounded-full overflow-hidden mt-3"
              >
                <span
                  className={`absolute inset-y-0 left-0 rounded-full ${tier.bar}`}
                  style={{
                    width: `${safePct}%`,
                    transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)',
                  }}
                />
              </div>
              {progressLabel && (
                <div className="font-script text-caption text-ink-whisper mt-1.5">
                  {progressLabel}
                </div>
              )}
            </div>
          )}
          {rarityCounts && (
            <div className="w-full pt-1">
              <RarityStrand counts={rarityCounts} compact />
            </div>
          )}
          </div>
        </aside>

        {/* Recto — consumer's working list. */}
        <div data-folio-recto="true" className="px-4 md:px-6 py-5 md:py-6 space-y-5">
          {children}
        </div>
      </div>
    </ParchmentCard>
  );
}

import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import RuneBadge from '../../components/journal/RuneBadge';
import RarityStrand from '../../components/atlas/RarityStrand';
import { tierForProgress, TIER_BADGE_TONE } from '../../components/atlas/mastery.constants';

/**
 * QuestFolio — the verso/recto shell shared by Ventures, Duties, Study,
 * Rituals, and Movement. Modelled on pages/achievements/FolioSpread.jsx
 * but parameterised so a tab can fill in its own letter / title / stats /
 * progress without dragging the skill-tree XP math along.
 *
 * Verso (left, ~220-260px desktop · top banner mobile): a soft summary
 *   panel with a tier chip, letter tile, stats and progress.
 *
 * Tier is carried the way the rest of the app carries state — PROGRESS_TIER's
 * `bar` and `chip` channels (the versal's gilt fill, the progress bar, the
 * stat values, and the kicker's badge tone) — rather than by an applied
 * ornament. See components/README.md → Atlas cohort.
 *
 * Recto (right): consumer-supplied children — the working list.
 *
 * No new tier ladders, halo colors, or keyframes — composition against
 * the existing Atlas cohort (per components/README.md guidance).
 */

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
  const safeStats = (stats ?? []).slice(0, 3);
  const firstLetter = (letter || title || '✦').toString().trim().charAt(0).toUpperCase() || '✦';
  // Phone-only condensed incipit: the same stats the full plate renders,
  // inlined as a single caption line ("12 done · 3 waiting"). The values wear
  // tier.chip here too — the full plate already tints its big numerals, and
  // without this the compact row was the one place tier went unsaid.
  const showProgress = Boolean(progressLabel) || safePct > 0;

  return (
    <ParchmentCard
      tone="bright"
      as="section"
      aria-label={`${title} overview`}
      className={`!p-0 overflow-hidden ${className}`}
    >
      <div className="relative grid grid-cols-1 md:grid-cols-[220px_1fr] lg:grid-cols-[260px_1fr]">
        {/* Summary divider on desktop. */}
        <div
          aria-hidden="true"
          className="hidden md:block absolute inset-y-4 left-[220px] lg:left-[260px] w-px bg-ink-page-shadow/30 pointer-events-none"
        />

        {/* Verso — the chapter incipit. Below md it condenses to a single
            compact row (~100px) so the working list starts near the top of
            a phone screen; the full illuminated plate is untouched at md+. */}
        <aside
          data-folio-verso="true"
          data-tier={tierKey}
          data-progress={Math.round(safePct)}
          className="relative bg-ink-page-aged/40 px-4 pt-4 pb-3 md:px-5 md:pt-7 md:pb-6 flex flex-col items-center text-center gap-3 border-b md:border-b-0 md:border-r border-ink-page-shadow/30"
        >
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
                className="font-display font-bold text-ink-primary text-lede leading-tight break-words"
              >
                {title}
              </h2>
              {safeStats.length > 0 && (
                <div className="text-caption font-body text-ink-whisper mt-0.5">
                  {safeStats.map((s, i) => (
                    <span key={`${s.label}-${i}`}>
                      {i > 0 && ' · '}
                      <span className={tier.chip}>{s.value}</span> {s.label}
                    </span>
                  ))}
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

          {/* Full summary — md+ only, with the same progress and stats. */}
          <div
            data-folio-verso-full="true"
            className="hidden w-full md:flex flex-col items-center text-center gap-3"
          >
          {kicker && (
            <RuneBadge tone={TIER_BADGE_TONE[tierKey] ?? 'ink'} variant="outlined">
              {kicker}
            </RuneBadge>
          )}
          {/* Soft letter tile shared with the Skills summary. */}
          <span
            aria-hidden="true"
            data-folio-medallion="true"
            className="relative inline-flex items-center justify-center rounded-3xl p-2 bg-ink-page-aged"
          >
            <span
              className="rounded-2xl bg-ink-page-rune-glow p-1"
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
              className="font-display font-bold text-ink-primary text-xl md:text-2xl leading-tight break-words"
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
                    <span className={`block font-display font-bold leading-none text-2xl ${tier.chip}`}>
                      {s.value}
                    </span>
                    <span className="block text-caption font-body text-ink-whisper mt-0.5">
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

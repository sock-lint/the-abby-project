import ParchmentCard from '../../components/journal/ParchmentCard';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import RarityStrand from '../../components/atlas/RarityStrand';
import { tierForProgress } from '../../components/atlas/mastery.constants';

/**
 * QuestFolio — the verso/recto shell shared by Ventures, Duties, Study,
 * Rituals, and Movement. Modelled on pages/achievements/FolioSpread.jsx
 * but parameterised so a tab can fill in its own letter / title / stats /
 * progress without dragging the skill-tree XP math along.
 *
 * Verso (left, ~220-260px desktop · top banner mobile): cloth headband
 *   tied to tier, brass-rimmed illuminated drop-cap, script kicker,
 *   display-serif title with foil-glint, stats row, progress bar,
 *   optional rarity strand.
 *
 * Recto (right): consumer-supplied children — the working list.
 *
 * No new tier ladders, halo colors, or keyframes — composition against
 * the existing Atlas cohort (per components/README.md guidance).
 */

const TIER_TONE = {
  locked: { headband: 'var(--color-headband-locked)', foilBottom: 'var(--color-ink-page-shadow)' },
  nascent: { headband: 'var(--color-headband-nascent)', foilBottom: 'var(--color-ember-deep)' },
  rising: { headband: 'var(--color-headband-rising)', foilBottom: 'var(--color-ember-deep)' },
  cresting: { headband: 'var(--color-headband-cresting)', foilBottom: 'var(--color-ember-deep)' },
  gilded: { headband: 'var(--color-headband-gilded)', foilBottom: 'var(--color-gold-leaf)' },
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
  const tone = TIER_TONE[tierKey] ?? TIER_TONE.rising;
  const safeStats = (stats ?? []).slice(0, 3);
  const firstLetter = (letter || title || '✦').toString().trim().charAt(0).toUpperCase() || '✦';

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

        {/* Verso — the chapter incipit. */}
        <aside
          data-folio-verso="true"
          data-tier={tierKey}
          data-progress={Math.round(safePct)}
          className="relative px-5 pt-7 pb-5 md:pb-6 flex flex-col items-center text-center gap-3 border-b md:border-b-0 md:border-r border-ink-page-shadow/30"
        >
          <span
            aria-hidden="true"
            data-folio-headband="true"
            className="absolute top-0 left-0 right-0 h-1.5"
            style={{
              backgroundColor: tone.headband,
              boxShadow:
                'inset 0 -1px 0 rgba(45, 31, 21, 0.35), inset 0 1px 0 rgba(255, 248, 224, 0.25)',
            }}
          />
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
                '--foil-tone-bottom': tone.foilBottom,
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
        </aside>

        {/* Recto — consumer's working list. */}
        <div data-folio-recto="true" className="px-4 md:px-6 py-5 md:py-6 space-y-5">
          {children}
        </div>
      </div>
    </ParchmentCard>
  );
}

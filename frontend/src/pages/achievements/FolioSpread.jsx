import ParchmentCard from '../../components/journal/ParchmentCard';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import SkillVerse from './SkillVerse';
import { countIlluminated, tierForProgress } from '../../components/atlas/mastery.constants';
import { XP_THRESHOLDS } from './skillTree.constants';

/**
 * FolioSpread — the open codex that a selected tome reveals. On desktop
 * it's a two-column parchment spread with a gutter shadow down the
 * center; on mobile it collapses into a single column with the hero as
 * a top banner.
 *
 * Verso (left, ~36%): category incipit with a huge illuminated drop-cap
 *   whose gilt fills with category progress, chapter mark in rune, name
 *   in script, and "N of M illuminated" + a level strap.
 *
 * Recto (right, flex): subjects rendered as ChapterRubric headers
 *   followed by SkillVerse rows. Empty subjects are skipped.
 */
export default function FolioSpread({ tree, onSelectSkill }) {
  if (!tree) return null;
  const { category, summary, subjects = [] } = tree;
  const level = summary?.level ?? 0;
  const totalXp = summary?.total_xp ?? 0;
  const next = XP_THRESHOLDS[level + 1] ?? XP_THRESHOLDS[6];
  const current = XP_THRESHOLDS[level] ?? 0;
  const span = Math.max(1, next - current);
  const inLevel = Math.max(0, totalXp - current);
  const levelPct = Math.min(100, (inLevel / span) * 100);
  // Cumulative across all levels — drives the verso drop-cap gilt fill so
  // the letter literally illuminates as the category matures.
  const shelfPct = Math.min(100, (totalXp / XP_THRESHOLDS[6]) * 100);
  const tier = tierForProgress({ unlocked: true, progressPct: shelfPct, level });
  const { illuminated, total } = countIlluminated(subjects);
  const maxed = level >= 6;
  const toNext = Math.max(0, next - totalXp);
  const firstLetter = (category?.name || '✦').trim().charAt(0).toUpperCase() || '✦';

  return (
    <ParchmentCard
      tone="bright"
      flourish
      as="section"
      aria-label={`${category?.name} folio`}
      className="!p-0 overflow-hidden"
    >
      <div className="relative grid grid-cols-1 md:grid-cols-[220px_1fr] lg:grid-cols-[260px_1fr]">
        {/* Gutter — a vertical fold shadow down the center of the spread on
            desktop. Decorative only. */}
        <div
          aria-hidden="true"
          className="hidden md:block absolute inset-y-4 left-[220px] lg:left-[260px] w-px bg-gradient-to-b from-transparent via-ink-page-shadow/60 to-transparent pointer-events-none"
        />

        {/* Verso — category hero. No §-numeral here: those belong to the
            subject rubrics on the recto so the hierarchy reads cleanly
            (category name · subject §I · subject §II …). */}
        <aside className="px-5 pt-6 pb-5 md:pb-6 flex flex-col items-center text-center gap-3 border-b md:border-b-0 md:border-r border-ink-page-shadow/30">
          <div className="font-rune text-micro uppercase tracking-wider text-ember-deep">
            · the codex of mastery ·
          </div>
          <IlluminatedVersal
            letter={firstLetter}
            progressPct={shelfPct}
            tier={tier}
            size="xl"
          />
          <div className="space-y-0.5">
            <div className="font-script text-sheikah-teal-deep text-caption leading-none">
              the atlas
            </div>
            <h2 className="font-display italic text-xl md:text-2xl leading-tight text-ink-primary">
              {category?.icon ? (
                <span aria-hidden="true" className="mr-1 opacity-80">
                  {category.icon}
                </span>
              ) : null}
              {category?.name}
            </h2>
          </div>
          <div className="flex items-center gap-4 pt-1">
            <div className="text-center">
              <div
                className={`font-display italic font-bold leading-none text-2xl ${
                  maxed ? 'text-gold-leaf' : tier.chip
                }`}
              >
                L{level}
              </div>
              <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-0.5">
                rank
              </div>
            </div>
            <div className="h-8 w-px bg-ink-page-shadow/40" aria-hidden="true" />
            <div className="text-center">
              <div className="font-display italic font-bold leading-none text-2xl text-ink-primary">
                {totalXp.toLocaleString()}
              </div>
              <div className="text-micro font-rune uppercase tracking-wider text-ink-whisper mt-0.5">
                total xp
              </div>
            </div>
          </div>
          <div className="pt-2 w-full border-t border-ink-page-shadow/30">
            <div
              role="progressbar"
              aria-label={`${category?.name} category progress`}
              aria-valuenow={Math.round(levelPct)}
              aria-valuemin={0}
              aria-valuemax={100}
              className="relative h-1.5 bg-ink-page-shadow/50 rounded-full overflow-hidden mt-3"
            >
              <span
                className={`absolute inset-y-0 left-0 rounded-full ${tier.bar}`}
                style={{ width: `${levelPct}%`, transition: 'width 600ms cubic-bezier(0.4, 0, 0.2, 1)' }}
              />
            </div>
            <div className="flex items-center justify-between text-caption text-ink-whisper mt-1.5">
              <span className="font-script">
                {illuminated} of {total} illuminated
              </span>
              <span className="font-rune text-micro uppercase tracking-wider">
                {maxed ? 'mastery sealed' : `${toNext.toLocaleString()} to L${level + 1}`}
              </span>
            </div>
          </div>
        </aside>

        {/* Recto — subjects + verses */}
        <div className="px-4 md:px-6 py-5 md:py-6 space-y-5">
          {subjects.length === 0 ? (
            <div className="font-script text-ink-whisper text-center py-8">
              This chapter is still blank — skills will ink in as the atlas grows.
            </div>
          ) : (
            subjects.map((subject, i) => {
              const skills = subject?.skills ?? [];
              if (skills.length === 0) return null;
              return (
                <section key={subject.id} className="space-y-2">
                  <ChapterRubric index={i} subject={subject} />
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-2 xl:gap-3">
                    {skills.map((skill, j) => (
                      <SkillVerse
                        key={skill.id}
                        skill={skill}
                        index={j}
                        onSelect={onSelectSkill}
                      />
                    ))}
                  </div>
                </section>
              );
            })
          )}
        </div>
      </div>
    </ParchmentCard>
  );
}

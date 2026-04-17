import { chapterMark } from './mastery.constants';

/**
 * ChapterRubric — medieval "rubric" header for a subject. A rubric in the
 * manuscript sense is the red (rubrum) headmark that names a section. Here
 * it's a left-dropped roman numeral in ember-deep, the subject glyph, the
 * title in a display serif, and a hair-rule that carries the eye into the
 * stanzas below. Deliberately not sticky — stanza lists are short enough
 * that a stable section break reads cleaner.
 */
export default function ChapterRubric({ index, subject }) {
  const summary = subject?.summary;
  return (
    <header className="pt-4 pb-1">
      <div className="flex items-baseline gap-3">
        <span
          aria-hidden="true"
          className="font-display italic text-xl md:text-2xl text-ember-deep leading-none select-none"
        >
          {chapterMark(index)}
        </span>
        {subject?.icon && (
          <span aria-hidden="true" className="text-xl leading-none">
            {subject.icon}
          </span>
        )}
        <h3 className="font-display italic text-lede md:text-xl text-ink-primary leading-tight truncate flex-1">
          {subject?.name}
        </h3>
        {summary && (
          <span className="text-caption text-ink-whisper font-rune uppercase tracking-wider shrink-0">
            L{summary.level} · {(summary.total_xp ?? 0).toLocaleString()} XP
          </span>
        )}
      </div>
      <div className="mt-2 h-px bg-gradient-to-r from-ember-deep/30 via-ink-page-shadow/60 to-transparent" />
    </header>
  );
}

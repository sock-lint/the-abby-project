import ChapterMarker from './ChapterMarker';

/**
 * ChapterRubric — a Meadow section heading with a numbered waypoint,
 * optional icon and supporting progress. Kept in normal document flow.
 *
 * Accepts either direct props (`name` / `icon` / `summary`) for general
 * surfaces, or the legacy `subject` object shape used by Skills'
 * FolioSpread. Direct props win when both are present.
 */
export default function ChapterRubric({ index, subject, name, icon, summary }) {
  const displayName = name ?? subject?.name;
  const displayIcon = icon ?? subject?.icon;
  const displaySummary = summary ?? subject?.summary;
  return (
    <header className="pt-4 pb-1">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3">
        <ChapterMarker index={index} />
        {displayIcon && (
          <span aria-hidden="true" className="text-xl leading-none">
            {displayIcon}
          </span>
        )}
        <h3 className="font-display font-bold text-lede md:text-xl text-ink-primary leading-tight break-words min-w-0 flex-1">
          {displayName}
        </h3>
        {displaySummary && (
          <span className="text-caption text-ink-whisper font-body shrink-0">
            L{displaySummary.level} · {(displaySummary.total_xp ?? 0).toLocaleString()} XP
          </span>
        )}
      </div>
      <div className="mt-2 h-px bg-ink-page-shadow/40" />
    </header>
  );
}

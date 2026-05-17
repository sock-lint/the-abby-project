import ParchmentCard from '../../components/journal/ParchmentCard';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import { formatDate } from '../../utils/format';

/**
 * FamilyTrialsFolio — parent-only roll-up of every child's active trial.
 * Wrapped in a ChapterRubric header (§V on the manuscript) so it reads as
 * its own section rather than a bare ParchmentCard, matching the
 * illuminated vocabulary used by the rest of the page.
 */
export default function FamilyTrialsFolio({ rows = [] }) {
  if (!rows.length) return null;

  return (
    <ParchmentCard tone="default" className="space-y-3">
      <ChapterRubric
        index={4}
        name="Family Trials"
        summary={null}
      />
      <div className="space-y-2">
        {rows.map((row) => (
          <div key={row.child_id} className="flex items-center gap-3">
            <div className="font-script text-body text-ink-primary w-28 shrink-0 truncate">
              {row.child_name}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex justify-between items-baseline gap-2">
                <span className="font-body text-body text-ink-secondary truncate">
                  {row.quest.definition.name}
                </span>
                <span className="font-rune text-caption text-ink-whisper tabular-nums shrink-0">
                  {row.quest.current_progress}/{row.quest.effective_target}
                </span>
              </div>
              <div className="h-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                  style={{ width: `${row.quest.progress_percent}%` }}
                />
              </div>
            </div>
            <div className="font-rune text-caption text-ink-whisper tabular-nums shrink-0 w-20 text-right">
              ends {formatDate(row.quest.end_date)}
            </div>
          </div>
        ))}
      </div>
    </ParchmentCard>
  );
}

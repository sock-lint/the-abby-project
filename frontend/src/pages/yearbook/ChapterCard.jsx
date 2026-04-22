import ProgressBar from '../../components/ProgressBar'
import TimelineEntry from './TimelineEntry'
import { RECAP_STAT_FIELDS } from './yearbook.constants'

function schoolDaysProgress(chapterYear) {
  // Aug 1 of chapter_year → Jul 31 of chapter_year+1. Percent elapsed.
  const start = new Date(chapterYear, 7, 1).getTime()
  const end = new Date(chapterYear + 1, 6, 31).getTime()
  const now = Date.now()
  if (now <= start) return 0
  if (now >= end) return 100
  return Math.round(((now - start) / (end - start)) * 100)
}

export default function ChapterCard({ chapter }) {
  const { label, is_current, stats, entries } = chapter
  const statLines = RECAP_STAT_FIELDS
    .map((f) => [f, stats?.[f.key]])
    .filter(([, v]) => v !== undefined && v !== null)

  return (
    <section className="parchment-card p-4 space-y-3" aria-labelledby={`chapter-${chapter.chapter_year}`}>
      <header className="flex items-baseline justify-between">
        <h3 id={`chapter-${chapter.chapter_year}`} className="text-lede font-serif">{label}</h3>
        {is_current && <span className="text-caption text-ink-whisper">in progress</span>}
      </header>

      {is_current && (
        <ProgressBar
          value={schoolDaysProgress(chapter.chapter_year)}
          aria-label={`${label} — days elapsed`}
        />
      )}

      {statLines.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-caption">
          {statLines.map(([field, value]) => (
            <div key={field.key}>
              <dt className="text-ink-whisper">{field.label}</dt>
              <dd className="text-body font-medium">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {entries?.length > 0 && (
        <ul className="divide-y divide-ink-whisper/10">
          {entries.map((entry) => (
            <TimelineEntry key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  )
}

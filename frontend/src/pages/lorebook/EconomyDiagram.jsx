import ParchmentCard from '../../components/journal/ParchmentCard';
import { ECONOMY_FLAGS, economyFlagLabel } from './lorebook.constants';

function Mark({ value }) {
  return (
    <span
      className={`inline-flex h-6 w-6 items-center justify-center rounded-full border text-caption font-rune ${
        value
          ? 'border-moss/40 bg-moss/15 text-moss-deep'
          : 'border-ink-whisper/25 bg-ink-page-aged/35 text-ink-whisper'
      }`}
      aria-label={value ? 'yes' : 'no'}
    >
      {value ? '✓' : '—'}
    </span>
  );
}

export default function EconomyDiagram({ entries = [] }) {
  return (
    <ParchmentCard variant="sealed" tone="bright" flourish seal="top-right" className="overflow-hidden">
      <div className="pr-10">
        <div className="font-script text-sheikah-teal-deep text-base">
          parent map · which action pays what
        </div>
        <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
          Economy Diagram
        </h2>
        <p className="mt-1 text-sm text-ink-secondary max-w-3xl">
          Money, Coins, XP, drops, quests, and streaks are separate channels.
          This table makes the “why doesn&apos;t homework pay coins?” answer
          visible at a glance.
        </p>
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="min-w-[760px] w-full border-collapse text-sm">
          <caption className="sr-only">
            Lorebook economy diagram showing which mechanics award each reward channel.
          </caption>
          <thead>
            <tr className="border-b border-ink-page-shadow">
              <th scope="col" className="py-2 pr-3 text-left font-display text-ink-primary">
                Entry
              </th>
              {ECONOMY_FLAGS.map((flag) => (
                <th
                  key={flag.key}
                  scope="col"
                  className="px-2 py-2 text-center font-display text-caption text-ink-secondary"
                >
                  {economyFlagLabel(flag.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr
                key={entry.slug}
                className="border-b border-ink-page-shadow/50 last:border-b-0"
                data-lorebook-economy-row={entry.slug}
              >
                <th scope="row" className="py-2 pr-3 text-left font-body">
                  <div className="font-medium text-ink-primary">{entry.title}</div>
                  <div className="text-tiny text-ink-whisper line-clamp-1">{entry.summary}</div>
                </th>
                {ECONOMY_FLAGS.map((flag) => (
                  <td key={flag.key} className="px-2 py-2 text-center">
                    <Mark value={!!entry.economy?.[flag.key]} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ParchmentCard>
  );
}

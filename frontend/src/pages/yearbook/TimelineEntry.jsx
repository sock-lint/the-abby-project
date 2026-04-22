import { useState } from 'react'
import { Lock } from 'lucide-react'
import { KIND_ICON } from './yearbook.constants'
import EntryDetailSheet from './EntryDetailSheet'
import RuneBadge from '../../components/journal/RuneBadge'
import { useAuth } from '../../hooks/useApi'

export default function TimelineEntry({ entry }) {
  const [open, setOpen] = useState(false)
  const { user } = useAuth()
  // Show the lock chip to parents only — Abby's own view of her private
  // journal never renders the lock (it would feel surveillance-y).
  const showLock =
    entry.kind === 'journal' &&
    entry.is_private &&
    user?.role === 'parent'

  return (
    <>
      <li>
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center gap-3 py-2 text-left hover:bg-ink-whisper/5"
        >
          <span aria-hidden="true" className="text-lede">{KIND_ICON[entry.kind] ?? '•'}</span>
          <span className="flex-1">
            <span className="flex items-center gap-2 text-body">
              <span>{entry.title}</span>
              {showLock && (
                <RuneBadge
                  tone="ink"
                  size="sm"
                  icon={<Lock size={10} aria-hidden="true" />}
                >
                  Private
                </RuneBadge>
              )}
            </span>
            <span className="block text-caption text-ink-whisper">{entry.occurred_on}</span>
          </span>
        </button>
      </li>
      {open && <EntryDetailSheet entry={entry} onClose={() => setOpen(false)} />}
    </>
  )
}

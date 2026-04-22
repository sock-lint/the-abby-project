import { useState } from 'react'
import { KIND_ICON } from './yearbook.constants'
import EntryDetailSheet from './EntryDetailSheet'

export default function TimelineEntry({ entry }) {
  const [open, setOpen] = useState(false)
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
            <span className="block text-body">{entry.title}</span>
            <span className="block text-caption text-ink-whisper">{entry.occurred_on}</span>
          </span>
        </button>
      </li>
      {open && <EntryDetailSheet entry={entry} onClose={() => setOpen(false)} />}
    </>
  )
}

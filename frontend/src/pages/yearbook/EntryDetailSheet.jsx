import { useState } from 'react'
import { Lock, Pencil } from 'lucide-react'
import BottomSheet from '../../components/BottomSheet'
import Button from '../../components/Button'
import RuneBadge from '../../components/journal/RuneBadge'
import JournalEntryFormModal from './JournalEntryFormModal'
import { useRole } from '../../hooks/useRole'

function todayISO() {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export default function EntryDetailSheet({ entry, onClose }) {
  const { user, isParent } = useRole()
  const [editing, setEditing] = useState(false)
  const isJournal = entry.kind === 'journal'
  const isOwner = isJournal && entry.user === user?.id
  const isSameDay = isJournal && entry.occurred_on === todayISO()
  const canEdit = isOwner && isSameDay
  const showLock = isJournal && entry.is_private && isParent

  if (editing) {
    return (
      <JournalEntryFormModal
        mode="edit"
        entry={entry}
        onClose={() => setEditing(false)}
        onSaved={() => {
          setEditing(false)
          onClose()
        }}
      />
    )
  }

  return (
    <BottomSheet title={entry.title} onClose={onClose}>
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-caption text-ink-whisper">
          <span>{entry.occurred_on}</span>
          {showLock && (
            <RuneBadge
              tone="ink"
              size="sm"
              icon={<Lock size={10} aria-hidden="true" />}
            >
              Private journal
            </RuneBadge>
          )}
        </div>
        {entry.summary && (
          <p className="text-body whitespace-pre-wrap font-body leading-relaxed">
            {entry.summary}
          </p>
        )}
        {entry.metadata?.gift_coins && (
          <p className="text-body">🎁 {entry.metadata.gift_coins} coins</p>
        )}
        {canEdit && (
          <div className="flex justify-end pt-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => setEditing(true)}
              className="flex items-center gap-2"
            >
              <Pencil size={14} aria-hidden="true" /> Edit
            </Button>
          </div>
        )}
      </div>
    </BottomSheet>
  )
}

import BottomSheet from '../../components/BottomSheet'

export default function EntryDetailSheet({ entry, onClose }) {
  return (
    <BottomSheet title={entry.title} onClose={onClose}>
      <div className="space-y-3 p-4">
        <p className="text-caption text-ink-whisper">{entry.occurred_on}</p>
        {entry.summary && <p className="text-body">{entry.summary}</p>}
        {entry.metadata?.gift_coins && (
          <p className="text-body">🎁 {entry.metadata.gift_coins} coins</p>
        )}
      </div>
    </BottomSheet>
  )
}

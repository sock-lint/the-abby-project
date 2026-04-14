import { useState } from 'react';
import BottomSheet from '../../../components/BottomSheet';
import { buttonPrimary, buttonSecondary } from '../../../constants/styles';

export default function RequestChangesModal({ onClose, onSubmit }) {
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!notes.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(notes.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <BottomSheet title="Request Changes" onClose={onClose} disabled={submitting}>
      <p className="text-sm text-ink-whisper">
        Tell the maker what needs to change before you approve this project.
      </p>
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="What should they fix or add?"
        autoFocus
        rows={4}
        className="w-full bg-ink-page border border-ink-page-shadow rounded-lg px-3 py-2 text-ink-primary text-base resize-none focus:outline-none focus:border-sheikah-teal-deep"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={submitting}
          className={`flex-1 py-3 ${buttonSecondary}`}
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting || !notes.trim()}
          className={`flex-1 py-3 disabled:cursor-not-allowed ${buttonPrimary}`}
        >
          {submitting ? 'Sending...' : 'Send'}
        </button>
      </div>
    </BottomSheet>
  );
}

import { useState } from 'react';
import { Lock, Mic, MicOff } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, TextAreaField } from '../../components/form';
import { formLabelClass } from '../../constants/styles';
import { useSpeechDictation } from '../../hooks/useSpeechDictation';
import { writeJournal, updateJournalEntry } from '../../api';

/**
 * JournalEntryFormModal — child-facing form for writing (or editing, same-day)
 * a private journal entry that appears on the Yearbook timeline.
 *
 * Props:
 *   mode      — "create" (default) or "edit"
 *   entry     — required when mode="edit"; prefills title + summary
 *   onSaved   — (entry) => void, called after a successful save
 *   onClose   — () => void
 *
 * Dictation uses the browser Web Speech API via useSpeechDictation. When the
 * API isn't available (Firefox, etc.) the mic button renders disabled with a
 * contextual aria-label.
 */
export default function JournalEntryFormModal({
  mode = 'create',
  entry,
  onSaved,
  onClose,
}) {
  const initialTitle = mode === 'edit' && entry ? entry.title || '' : '';
  const initialSummary = mode === 'edit' && entry ? entry.summary || '' : '';

  const [title, setTitle] = useState(initialTitle);
  const [summary, setSummary] = useState(initialSummary);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  // Dictated chunks append to summary with a trailing space (the hook
  // normalizes that) so the text reads naturally as it grows.
  const { start, stop, isListening, interim, supported } = useSpeechDictation({
    onFinal: (chunk) => {
      setSummary((prev) => (prev ? `${prev}${chunk}` : chunk));
    },
  });

  const handleMic = () => {
    if (!supported) return;
    if (isListening) stop();
    else start();
  };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      const payload = { title, summary };
      const saved =
        mode === 'edit'
          ? await updateJournalEntry(entry.id, payload)
          : await writeJournal(payload);
      onSaved?.(saved);
      onClose?.();
    } catch (err) {
      // A 403 here means the day rolled over while the modal was open —
      // the entry is locked. Present it as a read-only fact.
      if (err?.status === 403) {
        setError("That entry is locked now — it's part of your chronicle.");
      } else {
        setError(err?.message || 'Could not save your entry.');
      }
    } finally {
      setSaving(false);
    }
  };

  const primaryLabel = mode === 'edit' ? 'Update entry' : 'Save entry';
  const modalTitle =
    mode === 'edit' ? 'Edit your journal entry' : 'Write in your journal';
  const micAriaLabel = !supported
    ? 'Dictation not supported in this browser'
    : isListening
      ? 'Stop dictation'
      : 'Dictate';

  return (
    <BottomSheet title={modalTitle} onClose={onClose} disabled={saving}>
      <form onSubmit={submit} className="space-y-4">
        <TextField
          label="Title"
          placeholder="(leave blank — we'll use the first line)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />

        <div>
          <div className="flex items-end justify-between gap-2 mb-1">
            <label htmlFor="journal-body" className={`${formLabelClass} mb-0`}>
              What's on your mind?
            </label>
            <div className="relative">
              {isListening && (
                <span
                  aria-hidden="true"
                  className="absolute inset-0 rounded-full animate-rune-pulse"
                  style={{
                    background:
                      'radial-gradient(circle, var(--color-sheikah-teal) 0%, transparent 70%)',
                    opacity: 0.45,
                  }}
                />
              )}
              <IconButton
                type="button"
                aria-label={micAriaLabel}
                onClick={handleMic}
                disabled={!supported}
                className={`relative ${isListening ? 'text-ember-deep' : ''}`}
              >
                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </IconButton>
            </div>
          </div>
          <TextAreaField
            id="journal-body"
            rows={10}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Write or tap the mic to dictate…"
          />
          {isListening && interim && (
            <p className="font-script text-tiny text-sheikah-teal-deep italic mt-1.5">
              Listening… “{interim}”
            </p>
          )}
        </div>

        <ErrorAlert message={error} />

        <p className="flex items-center gap-1.5 font-script text-tiny text-ink-whisper italic">
          <Lock size={11} aria-hidden="true" />
          <span>Private to you. Mom &amp; Dad can read it.</span>
        </p>

        <div className="flex justify-end gap-2">
          <Button variant="ghost" type="button" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" disabled={saving}>
            {saving ? 'Saving…' : primaryLabel}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

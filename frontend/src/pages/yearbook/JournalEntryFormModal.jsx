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
  mode: initialMode = 'create',
  entry: initialEntry,
  onSaved,
  onClose,
}) {
  // Local mode/entry can flip from "create" to "edit" mid-session if the
  // server returns 409 on POST (a second entry was written between the
  // Quick Actions pre-check and the submit — rare, but it should not
  // feel like an error to the child).
  const [mode, setMode] = useState(initialMode);
  const [entry, setEntry] = useState(initialEntry || null);
  const [title, setTitle] = useState(
    initialMode === 'edit' && initialEntry ? initialEntry.title || '' : '',
  );
  const [summary, setSummary] = useState(
    initialMode === 'edit' && initialEntry ? initialEntry.summary || '' : '',
  );
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
      } else if (err?.status === 409 && err?.response?.existing) {
        // Raced against an earlier POST (rare — Quick Actions pre-checks).
        // Flip the modal into edit mode with the existing entry so the
        // child can merge their thought instead of seeing a dead-end error.
        const existing = err.response.existing;
        setMode('edit');
        setEntry(existing);
        setTitle(existing.title || '');
        // Keep whatever the child was typing in front of the existing
        // body so their in-flight words don't vanish.
        setSummary((current) => {
          const prior = existing.summary || '';
          if (!current) return prior;
          if (current === prior) return current;
          return `${prior}\n\n${current}`;
        });
        setError(
          "You already wrote today — we've loaded your entry so you can add to it.",
        );
      } else {
        setError(err?.message || 'Could not save your entry.');
      }
    } finally {
      setSaving(false);
    }
  };

  // A journal entry locks at the next local midnight. If the modal opens on a
  // prior-day entry (e.g. tap "today" right after midnight, or open from
  // history) the body becomes read-only — saving would 403 on the backend.
  // Compute "today" in local time (matches Django ``timezone.localdate()``)
  // and compare against ``entry.occurred_on`` (YYYY-MM-DD ISO string).
  const todayIso = new Date().toLocaleDateString('en-CA');
  const isLocked =
    mode === 'edit' && entry?.occurred_on && entry.occurred_on !== todayIso;

  const primaryLabel = mode === 'edit' ? 'Update entry' : 'Save entry';
  const modalTitle = isLocked
    ? 'Journal entry — locked'
    : mode === 'edit'
      ? 'Edit your journal entry'
      : 'Write in your journal';
  const micAriaLabel = !supported
    ? 'Dictation not supported in this browser'
    : isListening
      ? 'Stop dictation'
      : 'Dictate';

  return (
    <BottomSheet title={modalTitle} onClose={onClose} disabled={saving}>
      <form onSubmit={submit} className="space-y-4">
        {isLocked && (
          <p className="font-script text-xs px-3 py-2 rounded-lg border border-gold-leaf/40 bg-gold-leaf/10 text-ink-secondary flex items-start gap-2">
            <Lock size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              This entry is part of your chronicle now — the words stay as you wrote them.
            </span>
          </p>
        )}
        <TextField
          label="Title"
          placeholder="(leave blank — we'll use the first line)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isLocked}
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
                disabled={!supported || isLocked}
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
            disabled={isLocked}
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
            {isLocked ? 'Close' : 'Cancel'}
          </Button>
          {!isLocked && (
            <Button variant="primary" type="submit" disabled={saving}>
              {saving ? 'Saving…' : primaryLabel}
            </Button>
          )}
        </div>
      </form>
    </BottomSheet>
  );
}

import { useRef, useState } from 'react';
import { getToken } from '../../api/client';
import useMountedRef from '../../hooks/useMountedRef';
import { usePulse } from '../../providers/pulseContext';
import { Check, Heart, Lock, Mic, MicOff, PawPrint } from 'lucide-react';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, TextAreaField } from '../../components/form';
import { formLabelClass } from '../../constants/styles';
import { useSpeechDictation } from '../../hooks/useSpeechDictation';
import { useRole } from '../../hooks/useRole';
import { writeJournal, updateJournalEntry } from '../../api';
import { fieldErrors } from '../../utils/api';
import {
  clearJournalDraft, newJournalRequestId, readJournalDraft, storeJournalDraft,
} from './journalDraft';

// The Web Speech API reports failures as terse machine codes. Declining the
// mic prompt (or having it blocked at the OS level) is the most common
// first-tap outcome on a phone, and iOS re-asks per session in the installed
// app — without this the mic button just flickers and reads as broken.
const DICTATION_HINTS = {
  'not-allowed': 'Mic is blocked — allow microphone access in your settings, then tap again.',
  'service-not-allowed': 'Mic is blocked — allow microphone access in your settings, then tap again.',
  'audio-capture': "Can't find a microphone on this device.",
  'no-speech': "Didn't catch anything — tap the mic and try again.",
  network: 'Dictation needs a connection — type instead, or try again later.',
};

function dictationHint(code) {
  if (!code) return '';
  return DICTATION_HINTS[code] || 'Dictation stopped — tap the mic to try again.';
}

/**
 * JournalEntryFormModal — journal capture with a recoverable device draft,
 * same-day text edits, and an explicit family sharing choice.
 *
 * Props:
 *   mode      — "create" (default) or "edit"
 *   entry     — required when mode="edit"; prefills title + summary
 *   onSaved   — (entry, { mode }) => void, when saved confirmation closes;
 *               mode reflects any create → edit recovery after a 409
 *   onClose   — () => void
 *
 * Dictation uses the browser Web Speech API via useSpeechDictation. When the
 * API isn't available (Firefox, etc.) the mic button renders disabled with a
 * contextual aria-label.
 */
export default function JournalEntryFormModal(props) {
  const { user } = useRole();
  // An account change must remount capture state rather than persisting the
  // previous child's words under the next child's storage key.
  return (
    <JournalEntryForm
      key={`${user?.id ?? 'anonymous'}:${getToken()}:${props.mode ?? 'create'}:${props.entry?.id ?? 'new'}`}
      {...props}
      userId={user?.id}
    />
  );
}

function initialForm(userId, mode, entry) {
  const draft = readJournalDraft(userId);
  const matches = draft && (
    (mode === 'create' && draft.mode === 'create')
    || (mode === 'edit' && draft.mode === 'edit' && draft.entry_id === entry?.id)
    || (draft.pending?.method === 'post'
      && draft.client_entry_id === entry?.client_entry_id)
  );
  return {
    client_entry_id: matches ? draft.client_entry_id : newJournalRequestId(),
    mode: matches ? draft.mode : mode,
    entry: entry || null,
    title: matches ? draft.title : entry?.title || '',
    summary: matches ? draft.summary : entry?.summary || '',
    is_private: matches ? draft.is_private : entry?.is_private ?? true,
    pending: matches ? draft.pending : null,
    restored: Boolean(matches),
  };
}

async function saveWithDeadline(request) {
  let timer;
  try {
    return await Promise.race([
      request(),
      new Promise((_, reject) => {
        timer = window.setTimeout(() => reject(new Error('The connection took too long.')), 20000);
      }),
    ]);
  } finally {
    window.clearTimeout(timer);
  }
}

function JournalEntryForm({
  mode: initialMode = 'create',
  entry: initialEntry,
  userId,
  onSaved,
  onClose,
  surfaceClassName,
  surfaceStyle,
}) {
  const { refresh } = usePulse();
  const mounted = useMountedRef();
  const token = useRef(getToken());
  const [form, setForm] = useState(() => initialForm(userId, initialMode, initialEntry));
  const formRef = useRef(form);
  const { mode, entry, title, summary, is_private: isPrivate, pending } = form;
  const [storageState, setStorageState] = useState(form.restored ? 'saved' : 'idle');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const [savedEntry, setSavedEntry] = useState(null);

  const changeForm = (changes) => {
    const next = { ...formRef.current, ...changes };
    formRef.current = next;
    setStorageState(storeJournalDraft(userId, next) ? 'saved' : 'unavailable');
    setForm(next);
    return next;
  };
  const hasChanges = title !== (initialEntry?.title || '')
    || summary !== (initialEntry?.summary || '')
    || isPrivate !== (initialEntry?.is_private ?? true);
  // Stored drafts stay on the device when a sheet closes. Keep the standard
  // discard warning only when the browser could not preserve the words.
  const dirty = hasChanges && storageState !== 'saved' && !savedEntry;

  // Dictated chunks append to summary with a trailing space (the hook
  // normalizes that) so the text reads naturally as it grows.
  const {
    start, stop, isListening, interim, supported, error: dictationError,
  } = useSpeechDictation({
    onFinal: (chunk) => {
      const current = formRef.current;
      if (!saving && !current.pending) changeForm({ summary: `${current.summary}${chunk}` });
    },
  });

  const handleMic = () => {
    if (!supported) return;
    if (isListening) stop();
    else start();
  };

  const submit = async (e) => {
    e.preventDefault();
    if (saving) return;
    if (!pending && !isLocked && !title.trim() && !summary.trim()) {
      setError('Write a thought or a title before saving.');
      return;
    }
    stop?.();
    setSaving(true);
    setError('');
    setErrors({});
    const request = pending || {
      method: mode === 'edit' ? 'patch' : 'post',
      entry_id: entry?.id,
      payload: isLocked
        ? { is_private: isPrivate }
        : {
          title, summary, is_private: isPrivate,
          ...(mode === 'create' ? { client_entry_id: form.client_entry_id } : {}),
        },
    };
    // Persist the exact request before sending. If iOS closes the tab or a
    // response disappears, retrying checks the same save instead of creating
    // another reward-bearing contribution.
    changeForm({ pending: request });
    try {
      const saved = await saveWithDeadline(() => request.method === 'patch'
        ? updateJournalEntry(request.entry_id, request.payload)
        : writeJournal(request.payload));
      if (!mounted.current || getToken() !== token.current) return;
      clearJournalDraft(userId, form.client_entry_id, form);
      setSavedEntry(saved);
      // Refresh the shared header/Today balances from the server. Failure
      // here cannot undo the already confirmed journal save.
      void Promise.resolve().then(() => refresh()).catch(() => {});
    } catch (err) {
      if (!mounted.current || getToken() !== token.current) return;
      // A 403 here means the day rolled over while the modal was open —
      // the entry is locked. Present it as a read-only fact.
      if (err?.status === 403) {
        changeForm({ pending: null });
        setError("This entry can no longer be edited. You can still change its sharing setting.");
      } else if (err?.status === 409 && err?.response?.existing) {
        // Raced against an earlier POST (rare — Quick Actions pre-checks).
        // Flip the modal into edit mode with the existing entry so the
        // child can merge their thought instead of seeing a dead-end error.
        const existing = err.response.existing;
        // Append the new thought without losing the existing body.
        const prior = existing.summary || '';
        const merged = !summary || summary === prior ? prior : `${prior}\n\n${summary}`;
        // Private wins: words typed as private never become shared, and an
        // existing private entry stays private.
        changeForm({
          mode: 'edit', entry: existing, title: existing.title || '',
          summary: merged, is_private: isPrivate || existing.is_private !== false, pending: null,
        });
        setError(
          "You already wrote today — we've loaded your entry so you can add to it.",
        );
      } else if (err?.status >= 400 && err?.status < 500) {
        changeForm({ pending: null });
        const fields = fieldErrors(err);
        setErrors(fields);
        setError(Object.keys(fields).length ? 'Check the highlighted fields.' : err?.message || 'Could not save your entry.');
      } else {
        setError('We could not confirm the save. Your words are here; check the save when your connection returns.');
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

  const sharingChanged = isPrivate !== (entry?.is_private ?? true);
  const primaryLabel = pending ? 'Check save' : isLocked ? 'Update sharing' : mode === 'edit' ? 'Update entry' : 'Save entry';
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

  const finish = () => {
    onSaved?.(savedEntry, { mode });
    onClose?.();
  };

  if (savedEntry) {
    const receipt = savedEntry.reward_receipt;
    const newReceipt = mode === 'create' && !initialEntry?.id;
    const awarded = newReceipt && receipt?.status === 'awarded'
      && Number.isFinite(receipt.xp_awarded) && receipt.xp_awarded > 0;
    const coinsAwarded = newReceipt && receipt?.coin_status === 'awarded'
      && Number.isFinite(receipt.coins_awarded) && receipt.coins_awarded > 0;
    return (
      <BottomSheet title={mode === 'create' ? 'Memory saved' : 'Entry updated'} onClose={finish} surfaceClassName={surfaceClassName} surfaceStyle={surfaceStyle}>
        <div className="space-y-4 text-center">
          <div className="flex justify-center text-sheikah-teal-deep" aria-hidden="true">
            {awarded ? <PawPrint size={48} className="animate-rune-pulse" /> : <Check size={48} />}
          </div>
          <div role="status" aria-live="polite" className="space-y-2">
            <p className="font-display text-lede text-ink-primary">
              {awarded ? 'One more memory to grow with!' : 'Your words are saved in your journal.'}
            </p>
            {awarded && <p className="font-semibold text-body text-sheikah-teal-deep">+{receipt.xp_awarded} XP earned</p>}
            {coinsAwarded && <p className="font-semibold text-body text-sheikah-teal-deep">+{receipt.coins_awarded} Coins earned</p>}
            {newReceipt && receipt?.coin_status === 'already_received' && <p className="text-body text-ink-secondary">Today’s Coins were already received.</p>}
            {newReceipt && receipt?.coin_status === 'unavailable' && <p className="text-body text-ink-secondary">Your entry is saved. Its Coins could not be confirmed.</p>}
            {newReceipt && receipt?.status === 'unavailable' && (
              <p className="text-body text-ink-secondary">Your memory is saved. Its reward could not be confirmed.</p>
            )}
            {newReceipt && receipt?.status === 'not_eligible' && (
              <p className="text-body text-ink-secondary">This memory is saved without extra XP.</p>
            )}
            {mode === 'edit' && <p className="text-body text-ink-secondary">Updates keep your memory current without another reward.</p>}
          </div>
          <p className="text-body text-ink-secondary">
            {savedEntry.is_private === false
              ? 'Shared with parents in your family. They can leave you a response.'
              : 'Only you can read this entry in the app.'}
          </p>
          <Button variant="primary" onClick={finish} className="w-full">Done</Button>
        </div>
      </BottomSheet>
    );
  }

  return (
    <BottomSheet title={modalTitle} onClose={onClose} disabled={saving} dirty={dirty} surfaceClassName={surfaceClassName} surfaceStyle={surfaceStyle}>
      <form onSubmit={submit} className="space-y-4">
        {isLocked && (
          <p className="font-script text-xs px-3 py-2 rounded-lg border border-gold-leaf/40 bg-gold-leaf/10 text-ink-secondary flex items-start gap-2">
            <Lock size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
            <span>
              This entry can no longer be edited. You can still change its sharing setting.
            </span>
          </p>
        )}
        <p className="text-body text-ink-secondary">Write about anything, even a hard day. A few words count. When you save, find your entry in Memories → Journal.</p>
        <details open={Boolean(title)}>
          <summary className="min-h-11 flex items-center text-caption text-ink-secondary cursor-pointer">Add a title (optional)</summary>
          <TextField
            label="Title"
            placeholder="(leave blank — we'll use the first line)"
            value={title}
            onChange={(e) => changeForm({ title: e.target.value })}
            disabled={isLocked || saving || Boolean(pending)}
            error={errors.title}
          />
        </details>

        <div>
          <div className="flex items-end justify-between gap-2 mb-1">
            {/* intentional: hand-rolled label paired with TextAreaField id="journal-body"
                so the inline mic IconButton can sit on the label row. TextAreaField
                renders no label when prop is omitted; htmlFor/id keep a11y wiring intact. */}
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
                disabled={!supported || isLocked || saving || Boolean(pending)}
                className={`relative ${isListening ? 'text-ember-deep' : ''}`}
              >
                {isListening ? <MicOff size={18} /> : <Mic size={18} />}
              </IconButton>
            </div>
          </div>
          <TextAreaField
            id="journal-body"
            rows={5}
            value={summary}
            onChange={(e) => changeForm({ summary: e.target.value })}
            placeholder="Something from your day…"
            disabled={isLocked || saving || Boolean(pending)}
            error={errors.summary}
          />
          {isListening && interim && (
            <p className="font-script text-tiny text-sheikah-teal-deep italic mt-1.5">
              Listening… “{interim}”
            </p>
          )}
          {!isListening && dictationError && (
            <p className="font-script text-tiny text-ember-deep italic mt-1.5">
              {dictationHint(dictationError)}
            </p>
          )}
        </div>

        <p className="text-caption text-ink-secondary">Need an idea? Something you noticed, something you tried, or someone you appreciate.</p>
        {!isLocked && <p className="text-caption text-ink-secondary">The first new entry each day can earn writing XP and a 2 Coin daily bonus, alongside normal journal progress. More words or happier thoughts do not earn more. Updates give no extra reward.</p>}
        <ErrorAlert message={error} />

        {/* intentional: checkbox is outside the text/select form primitives;
            its enclosing label supplies an accessible name and 44px target. */}
        <label className="flex items-center gap-3 min-h-11 text-body text-ink-primary">
          <input
            type="checkbox"
            checked={!isPrivate}
            onChange={(e) => changeForm({ is_private: !e.target.checked })}
            disabled={saving || Boolean(pending)}
            className="h-5 w-5 shrink-0 accent-sheikah-teal-deep"
          />
          Share with parents in my family
        </label>
        <p className="flex items-start gap-2 text-caption text-ink-secondary">
          {isPrivate ? <Lock size={14} aria-hidden="true" /> : <Heart size={14} aria-hidden="true" />}
          <span>{isPrivate ? 'Only you can read this entry in the app.' : 'Parents in your family can read this entry and leave a response.'}</span>
        </p>
        <p role="status" aria-live="polite" className="text-caption text-ink-whisper">
          {saving
            ? 'Saving to your journal…'
            : pending
              ? 'Save not confirmed yet. Check save to safely try again.'
              : storageState === 'saved'
                ? 'Draft kept on this device. It is not saved in your journal yet.'
                : storageState === 'unavailable'
                  ? 'This browser cannot keep a draft. Keep this window open until you save.'
                  : 'Save when you are ready to keep this memory.'}
        </p>
        {storageState === 'unavailable' && pending && (
          <p className="text-caption text-ember-deep">This browser cannot keep a draft. Keep this window open until the save is confirmed.</p>
        )}

        <div className="flex justify-end gap-2">
          {/* With unavailable storage, dismiss through the sheet's guarded
              close control so an unsaved capture cannot bypass its warning. */}
          {!dirty && (
            <Button variant="ghost" type="button" onClick={onClose} disabled={saving}>
              {storageState === 'saved' && hasChanges ? 'Keep draft & close' : 'Close'}
            </Button>
          )}
          {(!isLocked || sharingChanged || pending) && (
            <Button variant="primary" type="submit" loading={saving}>
              {primaryLabel}
            </Button>
          )}
        </div>
      </form>
    </BottomSheet>
  );
}

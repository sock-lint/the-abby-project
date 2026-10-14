import { useEffect, useId, useRef, useState } from 'react';
import { Heart, Sparkles } from 'lucide-react';
import { CoinIcon } from '../../components/icons/JournalIcons';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import { TextAreaField, TextField } from '../../components/form';
import ErrorAlert from '../../components/ErrorAlert';
import { getWellbeingToday, submitGratitude } from '../../api';
import { useApi } from '../../hooks/useApi';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';

const IDEAS = [
  { label: 'Something I noticed', placeholder: 'Something I noticed today…' },
  { label: 'Something I tried', placeholder: 'Something I tried today…' },
  { label: 'Someone I appreciate', placeholder: 'Someone I appreciate…' },
];

function filledLines(lines) {
  return lines.map((line) => line.trim()).filter(Boolean);
}

/**
 * WellbeingCard — a daily affirmation and an optional personal note.
 *
 * Lives on child Today after tasks, projects and the pinned goal. Soft tone —
 * never punishes, never streaks, no
 * notifications. The first-of-day gratitude submit pays a small coin
 * trickle (see apps/wellbeing/services.py); subsequent edits same-day
 * don't double-pay.
 */
export default function WellbeingCard() {
  const { data, loading, setData } = useApi(getWellbeingToday);
  const [lines, setLines] = useState(['', '', '']);
  const [showMore, setShowMore] = useState(false);
  const [idea, setIdea] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  // ``coinFlash`` shows a one-shot "+2 coins" chip after a freshly-paid
  // submit. Cleared after 3s so it doesn't sit on the card forever.
  const [coinFlash, setCoinFlash] = useState(0);
  const flashTimeoutRef = useRef(null);
  const noteRef = useRef(null);
  const headingId = useId();
  const cleaned = filledLines(lines);
  const saved = Array.isArray(data?.gratitude_lines) ? data.gratitude_lines : [];
  const changed = Boolean(data) && JSON.stringify(cleaned) !== JSON.stringify(saved);
  usePwaUpdateGuard(working || changed);

  // Hydrate the inputs when today's row first loads or the user-saved
  // lines change underneath us.
  useEffect(() => {
    if (!data) return;
    const saved = Array.isArray(data.gratitude_lines) ? data.gratitude_lines : [];
    setLines([
      saved[0] || '',
      saved[1] || '',
      saved[2] || '',
    ]);
    setShowMore(saved.length > 1);
  }, [data]);

  useEffect(() => () => {
    if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
  }, []);

  if (loading) {
    return (
      <ParchmentCard tone="default" className="p-4">
        <div className="font-script text-caption text-ink-whisper">loading today's note…</div>
      </ParchmentCard>
    );
  }
  if (!data) return null;

  const affirmation = data.affirmation || {};
  const alreadyPaid = !!data.gratitude_paid;
  const reward = data.coin_reward ?? 2;
  const hasSavedNote = saved.length > 0;
  const noteStatus = hasSavedNote
    ? changed ? 'Unsaved changes' : 'Saved for today'
    : cleaned.length > 0 ? 'Ready to save' : 'One short line is enough.';

  const updateLine = (idx, value) => {
    setLines((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  const handleSave = async () => {
    if (working || cleaned.length === 0) return;
    setError('');
    setWorking(true);
    try {
      const result = await submitGratitude(cleaned);
      // The saved response includes today's lines and payment flag. A second
      // fetch could fail or overwrite this confirmation with an older result.
      setData(result);
      if (result?.freshly_paid) {
        setCoinFlash(result.coin_awarded || 0);
        if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
        flashTimeoutRef.current = setTimeout(() => setCoinFlash(0), 3200);
      }
    } catch (e) {
      setError(e.message || 'Could not save your note. Try again.');
    } finally {
      setWorking(false);
    }
  };

  return (
    <ParchmentCard tone="default" flourish className="space-y-4 relative overflow-hidden">
      <header className="flex items-start gap-3">
        <span className="text-rose mt-1" aria-hidden="true">
          <Heart size={18} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-script text-xs text-royal uppercase tracking-wider">
            today's note
          </div>
          <h2
            id={headingId}
            className="font-body font-bold text-lg text-ink-primary leading-tight mt-0.5"
          >
            For you, today
          </h2>
        </div>
      </header>

      {affirmation.text && (
        <blockquote
          className="font-script text-lede text-ink-primary leading-snug border-l-2 border-gold-leaf/60 pl-3 italic"
          aria-label="today's affirmation"
        >
          {affirmation.text}
        </blockquote>
      )}

      <div>
        <h3 className="font-body font-bold text-base text-ink-primary mb-2">
          A little note about your day
        </h3>
        <p className="font-body text-caption text-ink-secondary mb-3">
          Write about anything, even a hard day. A few words count.
        </p>
        <div className="space-y-2">
          <TextAreaField
            ref={noteRef}
            label="Today's note"
            value={lines[0]}
            onChange={(e) => updateLine(0, e.target.value)}
            placeholder={idea?.placeholder || 'Something from your day…'}
            rows={3}
            maxLength={data.max_line_chars || 200}
            disabled={working}
          />
          <details>
            <summary className="font-body text-caption text-ink-secondary cursor-pointer min-h-11 flex items-center">
              Need an idea? (optional)
            </summary>
            <div className="flex flex-wrap gap-2" aria-label="Optional writing ideas">
              {IDEAS.map((prompt) => (
                <Button
                  key={prompt.label}
                  variant="secondary"
                  size="sm"
                  aria-pressed={idea === prompt}
                  disabled={working}
                  onClick={() => { setIdea(prompt); noteRef.current?.focus(); }}
                >
                  {prompt.label}
                </Button>
              ))}
            </div>
          </details>
          {showMore ? (
            <div className="space-y-2">
              <TextField
                label="Another thought (optional)"
                value={lines[1]}
                onChange={(e) => updateLine(1, e.target.value)}
                maxLength={data.max_line_chars || 200}
                disabled={working}
              />
              <TextField
                label="One more thought (optional)"
                value={lines[2]}
                onChange={(e) => updateLine(2, e.target.value)}
                maxLength={data.max_line_chars || 200}
                disabled={working}
              />
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              disabled={working}
              onClick={() => setShowMore(true)}
            >
              Add more thoughts (optional)
            </Button>
          )}
        </div>
        {!alreadyPaid && (
          <p className="font-script text-caption text-ink-secondary mt-3">
            first save today earns +{reward}{' '}
            <CoinIcon size={12} className="inline text-gold-leaf" aria-hidden="true" />
          </p>
        )}
      </div>

      <ErrorAlert message={error} />

      <div className="flex items-center justify-between gap-3">
        <span role="status" className="font-body text-caption text-ink-secondary">
          {noteStatus}
        </span>
        <Button
          variant="primary"
          size="sm"
          onClick={handleSave}
          disabled={working || cleaned.length === 0}
        >
          {working ? 'Saving…' : hasSavedNote ? 'Update' : 'Save'}
        </Button>
      </div>

      {coinFlash > 0 && (
        <div
          role="status"
          aria-label="Daily note reward"
          className="absolute top-3 right-3 inline-flex items-center gap-1 font-script text-caption text-gold-leaf bg-ink-page-aged/90 rounded-full px-2.5 py-1 shadow-sm border border-gold-leaf/40"
        >
          <Sparkles size={11} aria-hidden="true" />
          +{coinFlash} <CoinIcon size={11} aria-hidden="true" />
        </div>
      )}
    </ParchmentCard>
  );
}

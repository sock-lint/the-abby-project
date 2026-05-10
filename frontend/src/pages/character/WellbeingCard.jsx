import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Heart, Coins, Sparkles } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import { TextField } from '../../components/form';
import ErrorAlert from '../../components/ErrorAlert';
import { getWellbeingToday, submitGratitude } from '../../api';
import { useApi } from '../../hooks/useApi';

// Mirrors apps/wellbeing/services.py::MAX_LINES — a small UI hint when
// the field count is hardcoded against the same constant on both sides.
const MAX_LINES = 3;

// The three line placeholder copies rotate by day-of-week so the prompt
// doesn't read identically every visit but stays predictable enough that
// kids learn the rhythm. Order intentionally varies — small/people/moment
// is the Finch-y "tiny things" lens. Index 0 is what you'd write first.
const PROMPT_SETS = [
  ['something small', 'someone who helped', 'a moment that felt good'],
  ['a kind thing', 'a soft thing', 'a brave thing'],
  ['something I noticed', 'someone I missed', 'something I learned'],
];

function promptsForToday() {
  const dow = new Date().getDay();
  return PROMPT_SETS[dow % PROMPT_SETS.length];
}

/**
 * WellbeingCard — Finch-inspired daily affirmation + gratitude pad.
 *
 * Lives on the Sigil Frontispiece between the hero frontispiece and the
 * cosmetic chapters. Soft tone — never punishes, never streaks, no
 * notifications. The first-of-day gratitude submit pays a small coin
 * trickle (see apps/wellbeing/services.py); subsequent edits same-day
 * don't double-pay.
 */
export default function WellbeingCard() {
  const { data, loading, reload } = useApi(getWellbeingToday);
  const [lines, setLines] = useState(['', '', '']);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  // ``coinFlash`` shows a one-shot "+2 coins" chip after a freshly-paid
  // submit. Cleared after 3s so it doesn't sit on the card forever.
  const [coinFlash, setCoinFlash] = useState(0);
  const flashTimeoutRef = useRef(null);
  const headingId = useId();

  const prompts = useMemo(promptsForToday, []);

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
  }, [data]);

  useEffect(() => () => {
    if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
  }, []);

  if (loading) {
    return (
      <ParchmentCard tone="default" className="p-4">
        <div className="font-script text-sm text-ink-whisper">loading today's note…</div>
      </ParchmentCard>
    );
  }
  if (!data) return null;

  const affirmation = data.affirmation || {};
  const alreadyPaid = !!data.gratitude_paid;
  const reward = data.coin_reward ?? 2;

  const updateLine = (idx, value) => {
    setLines((prev) => {
      const next = [...prev];
      next[idx] = value;
      return next;
    });
  };

  const handleSave = async () => {
    setError('');
    const cleaned = lines.map((line) => (line || '').trim()).filter(Boolean);
    if (cleaned.length === 0) {
      setError('Write at least one line — anything counts.');
      return;
    }
    setWorking(true);
    try {
      const result = await submitGratitude(cleaned);
      if (result?.freshly_paid) {
        setCoinFlash(result.coin_awarded || 0);
        if (flashTimeoutRef.current) clearTimeout(flashTimeoutRef.current);
        flashTimeoutRef.current = setTimeout(() => setCoinFlash(0), 3200);
      }
      reload();
    } catch (e) {
      setError(e.message || 'Could not save your gratitude lines.');
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
            className="font-display italic text-lg text-ink-primary leading-tight mt-0.5"
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
        <div className="font-display italic text-base text-ink-primary mb-2">
          Three small things you're grateful for
        </div>
        <p className="font-script text-tiny text-ink-whisper mb-3">
          jot one or three — short is fine, blanks are fine
          {!alreadyPaid && (
            <>
              {' '}· first save today earns +{reward}{' '}
              <Coins size={10} className="inline text-gold-leaf" aria-hidden="true" />
            </>
          )}
        </p>
        <div className="space-y-2">
          {[0, 1, 2].map((idx) => (
            <TextField
              key={idx}
              aria-label={`Gratitude line ${idx + 1}`}
              value={lines[idx]}
              onChange={(e) => updateLine(idx, e.target.value)}
              placeholder={prompts[idx]}
              maxLength={data.max_line_chars || 200}
              disabled={working}
            />
          ))}
        </div>
      </div>

      <ErrorAlert message={error} />

      <div className="flex items-center justify-between gap-3">
        <span className="font-script text-tiny text-ink-whisper">
          {lines.filter((line) => line.trim()).length}/{MAX_LINES} jotted
        </span>
        <Button
          variant="primary"
          size="sm"
          onClick={handleSave}
          disabled={working}
        >
          {working ? 'Saving…' : alreadyPaid ? 'Update' : 'Save'}
        </Button>
      </div>

      {coinFlash > 0 && (
        <div
          role="status"
          className="absolute top-3 right-3 inline-flex items-center gap-1 font-script text-sm text-gold-leaf bg-ink-page-aged/90 rounded-full px-2.5 py-1 shadow-sm border border-gold-leaf/40"
        >
          <Sparkles size={11} aria-hidden="true" />
          +{coinFlash} <Coins size={11} aria-hidden="true" />
        </div>
      )}
    </ParchmentCard>
  );
}

import { useState } from 'react';
import { Play, CheckCircle2 } from 'lucide-react';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import Button from '../../../components/Button';
import ErrorAlert from '../../../components/ErrorAlert';
import { useChecklist } from './useChecklist';

/**
 * DevToolCard — uniform card wrapper for every Test-tab tool.
 *
 * Each card pairs a title + description with a content slot (inputs +
 * action button). Renders an inline "Last result" line when ``onRun``
 * resolves, an ErrorAlert when it rejects. Result auto-clears after a
 * new submission so stale chips don't accumulate.
 *
 * Children should hand back a function via ``buildAction`` that the card
 * calls when the user clicks "Fire". This keeps each card tiny — just
 * its inputs + a closure that maps them onto the api function.
 *
 * Pass ``checklistId`` to enable the "Mark verified" flow — after a
 * successful fire, a small ghost button appears next to the result
 * that ticks the linked row in ``ChecklistRail``. The id matches the
 * stable ``<!-- id:slug -->`` annotation on the row in
 * ``docs/manual-testing.md``.
 */
export default function DevToolCard({
  title,
  description,
  buildAction,
  buttonLabel = 'Fire',
  formatResult = defaultFormat,
  checklistId,
  children,
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const { mark, isChecked } = useChecklist();
  const alreadyVerified = checklistId ? isChecked(checklistId) : false;

  const handleRun = async () => {
    setBusy(true);
    setError('');
    setResult(null);
    try {
      const res = await buildAction();
      setResult(res);
    } catch (e) {
      setError(e?.response?.detail || e?.message || 'Failed.');
    } finally {
      setBusy(false);
    }
  };

  const handleMarkVerified = () => {
    if (checklistId) mark(checklistId);
  };

  return (
    <ParchmentCard className="p-4 space-y-3">
      <div>
        <h3 className="font-display italic text-lg text-ink-primary">{title}</h3>
        {description ? (
          <p className="text-caption text-ink-secondary mt-1 leading-relaxed">{description}</p>
        ) : null}
      </div>

      <div className="space-y-2">{children}</div>

      <div className="flex items-center gap-3 flex-wrap">
        <Button
          onClick={handleRun}
          disabled={busy}
          className="flex items-center gap-1"
        >
          <Play size={14} /> {busy ? 'Working…' : buttonLabel}
        </Button>
        {result ? (
          <span className="text-caption text-moss font-script">
            {formatResult(result)}
          </span>
        ) : null}
        {result && checklistId ? (
          alreadyVerified ? (
            <span className="text-caption text-ink-secondary font-script italic">
              marked verified
            </span>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleMarkVerified}
              className="flex items-center gap-1"
            >
              <CheckCircle2 size={12} /> Mark verified
            </Button>
          )
        ) : null}
      </div>

      {error ? <ErrorAlert message={error} /> : null}
    </ParchmentCard>
  );
}

function defaultFormat(res) {
  if (typeof res === 'string') return res;
  if (res && typeof res === 'object') {
    // Show the first scalar field; full object is on the dev console.
    for (const [k, v] of Object.entries(res)) {
      if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') {
        return `✓ ${k}: ${v}`;
      }
    }
    return '✓ done';
  }
  return '✓ done';
}

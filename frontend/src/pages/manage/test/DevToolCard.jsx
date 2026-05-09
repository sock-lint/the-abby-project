import { useState } from 'react';
import { Play } from 'lucide-react';
import ParchmentCard from '../../../components/journal/ParchmentCard';
import Button from '../../../components/Button';
import ErrorAlert from '../../../components/ErrorAlert';

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
 */
export default function DevToolCard({
  title,
  description,
  buildAction,
  buttonLabel = 'Fire',
  formatResult = defaultFormat,
  children,
}) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

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

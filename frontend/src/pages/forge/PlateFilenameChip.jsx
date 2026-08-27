import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import IconButton from '../../components/IconButton';

/**
 * PlateFilenameChip — the minted plate filename, rendered loud.
 *
 * This string is the entire flow. On approval the app mints
 * `req-0042-dragon` and the parent must save the sliced plate as
 * `req-0042-dragon.3mf`; the MQTT listener then matches the printer's
 * reported `subtask_name` against it by exact equality. Get the name wrong
 * and the print lands as an unlinked job someone has to hand-link. So it
 * gets a monospace slab, a copy button, and a one-line reason.
 *
 * Shared by PrintRequestCard (the standing reminder) and ApprovalSheet
 * (the moment the parent is about to slice).
 */
export default function PlateFilenameChip({ filename, hint, className = '' }) {
  const [copied, setCopied] = useState(false);

  if (!filename) return null;

  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(filename);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard is permission-gated and absent on some in-app browsers.
      // The filename is on screen either way, so a failed copy is not an
      // error worth interrupting the parent over.
      setCopied(false);
    }
  };

  return (
    <div
      className={`rounded-lg border border-gold-leaf/50 bg-gold-leaf/10 px-3 py-2 ${className}`}
    >
      <div className="font-rune text-micro uppercase tracking-wider text-ember-deep">
        Save the sliced plate as
      </div>
      <div className="flex items-center gap-2 mt-1">
        <code className="flex-1 min-w-0 font-mono text-body text-ink-primary break-all">
          {filename}
        </code>
        <IconButton
          aria-label={`Copy plate filename ${filename}`}
          onClick={copy}
          variant="secondary"
          size="sm"
          className="shrink-0"
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </IconButton>
      </div>
      {copied && (
        <div role="status" className="font-script text-caption text-moss mt-1">
          Copied
        </div>
      )}
      <div className="font-script text-caption text-ink-whisper mt-1">
        {hint || 'The printer reports this name back, which is how the job finds this request.'}
      </div>
    </div>
  );
}

import { useState } from 'react';
import { Sparkles, X } from 'lucide-react';
import IconButton from '../IconButton';

function plural(count, noun) {
  return `${count} ${noun}${count !== 1 ? 's' : ''}`;
}

/**
 * SinceLastVisitCard — dismissible "while you were away" strip for the
 * child dashboard. Accepts the dashboard payload's `since_last_visit`
 * block (`{last_seen_at, badges_earned, coins_earned, approvals}` or
 * null on first visit). Renders nothing when there's nothing to tell —
 * rapid refreshes naturally produce all-zero summaries.
 */
export default function SinceLastVisitCard({ summary }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed || !summary) return null;

  const { badges_earned = 0, approvals = 0, coins_earned = 0 } = summary;
  const parts = [];
  if (badges_earned > 0) parts.push(`${plural(badges_earned, 'badge')} earned`);
  if (approvals > 0) parts.push(plural(approvals, 'approval'));
  if (coins_earned > 0) parts.push(`+${coins_earned} coins`);
  if (parts.length === 0) return null;

  return (
    <div
      role="status"
      className="rounded-lg border border-gold-leaf/40 bg-gold-leaf/10 px-4 py-2 text-body text-ink-primary flex items-start gap-3"
    >
      <Sparkles size={16} className="text-gold-leaf shrink-0 mt-1" aria-hidden="true" />
      <span className="flex-1 font-script">
        Since you were here last: {parts.join(' · ')}
      </span>
      <IconButton
        size="sm"
        onClick={() => setDismissed(true)}
        aria-label="Dismiss what's new"
      >
        <X size={16} />
      </IconButton>
    </div>
  );
}

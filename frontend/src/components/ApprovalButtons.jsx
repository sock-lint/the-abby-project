import { Check, X } from 'lucide-react';

// Bumped to 44px min-height per the 2026 mobile-tap audit. Parents triage
// approvals in line at the grocery / between meetings — the prior ~28px
// row was easy to misclick on small screens.
export default function ApprovalButtons({ onApprove, onReject, approveLabel = 'Approve', rejectLabel = 'Reject' }) {
  return (
    <div className="flex gap-2">
      <button
        type="button"
        onClick={onApprove}
        className="flex items-center justify-center gap-1.5 min-h-[44px] bg-moss/20 hover:bg-moss/30 text-moss-deep text-sm font-medium px-4 py-2 rounded-lg border border-moss/40 transition-colors"
      >
        <Check size={16} /> {approveLabel}
      </button>
      <button
        type="button"
        onClick={onReject}
        className="flex items-center justify-center gap-1.5 min-h-[44px] bg-ember/20 hover:bg-ember/30 text-ember-deep text-sm font-medium px-4 py-2 rounded-lg border border-ember/40 transition-colors"
      >
        <X size={16} /> {rejectLabel}
      </button>
    </div>
  );
}

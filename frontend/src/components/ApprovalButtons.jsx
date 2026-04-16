import { Check, X } from 'lucide-react';

export default function ApprovalButtons({ onApprove, onReject, approveLabel = 'Approve', rejectLabel = 'Reject' }) {
  return (
    <div className="flex gap-2">
      <button
        onClick={onApprove}
        className="flex items-center gap-1 bg-moss/20 hover:bg-moss/30 text-moss-deep text-xs px-3 py-1.5 rounded-lg border border-moss/40 transition-colors"
      >
        <Check size={14} /> {approveLabel}
      </button>
      <button
        onClick={onReject}
        className="flex items-center gap-1 bg-ember/20 hover:bg-ember/30 text-ember-deep text-xs px-3 py-1.5 rounded-lg border border-ember/40 transition-colors"
      >
        <X size={14} /> {rejectLabel}
      </button>
    </div>
  );
}

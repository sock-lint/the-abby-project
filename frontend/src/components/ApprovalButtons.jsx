import { Check, X } from 'lucide-react';

export default function ApprovalButtons({ onApprove, onReject, approveLabel = 'Approve', rejectLabel = 'Reject' }) {
  return (
    <div className="flex gap-2">
      <button
        onClick={onApprove}
        className="flex items-center gap-1 bg-green-500/20 hover:bg-green-500/30 text-green-300 text-xs px-3 py-1.5 rounded-lg border border-green-500/30"
      >
        <Check size={14} /> {approveLabel}
      </button>
      <button
        onClick={onReject}
        className="flex items-center gap-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs px-3 py-1.5 rounded-lg border border-red-500/30"
      >
        <X size={14} /> {rejectLabel}
      </button>
    </div>
  );
}

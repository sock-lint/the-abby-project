import ApprovalQueue from '../../components/ApprovalQueue';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { formatDateTime } from '../../utils/format';

export default function RedemptionApprovalQueue({ pending, onApprove, onReject }) {
  return (
    <ApprovalQueue
      items={pending}
      title="Pending Approvals"
      onApprove={onApprove}
      onReject={onReject}
    >
      {({ item: r, actions }) => (
        <ParchmentCard key={r.id} className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">
              {r.user_name} → {r.reward.icon} {r.reward.name}
            </div>
            <div className="text-xs text-ink-whisper">
              {r.coin_cost_snapshot} coins • {formatDateTime(r.requested_at)}
            </div>
          </div>
          {actions}
        </ParchmentCard>
      )}
    </ApprovalQueue>
  );
}

import ApprovalQueue from '../../components/ApprovalQueue';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { formatDateTime } from '../../utils/format';

export default function RedemptionApprovalQueue({ pending, onApprove, onReject }) {
  return (
    <ApprovalQueue
      items={pending}
      onApprove={onApprove}
      onReject={onReject}
    >
      {({ item: r, actions }) => (
        <ParchmentCard key={r.id} className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="w-full min-w-0 break-words sm:w-auto sm:flex-1">
            <div className="font-body text-body font-medium">
              {r.user_name} → {r.reward.icon} {r.reward.name}
            </div>
            <div className="font-script text-caption text-ink-whisper">
              {r.coin_cost_snapshot} coins • {formatDateTime(r.requested_at)}
            </div>
          </div>
          {actions}
        </ParchmentCard>
      )}
    </ApprovalQueue>
  );
}

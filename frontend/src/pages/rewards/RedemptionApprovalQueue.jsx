import ApprovalQueue from '../../components/ApprovalQueue';
import Card from '../../components/Card';
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
        <Card key={r.id} className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">
              {r.user_name} → {r.reward.icon} {r.reward.name}
            </div>
            <div className="text-xs text-forge-text-dim">
              {r.coin_cost_snapshot} coins • {formatDateTime(r.requested_at)}
            </div>
          </div>
          {actions}
        </Card>
      )}
    </ApprovalQueue>
  );
}

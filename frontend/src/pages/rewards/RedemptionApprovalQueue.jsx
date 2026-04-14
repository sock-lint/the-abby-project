import ApprovalButtons from '../../components/ApprovalButtons';
import Card from '../../components/Card';
import { formatDateTime } from '../../utils/format';

export default function RedemptionApprovalQueue({ pending, onApprove, onReject }) {
  if (!pending.length) return null;
  return (
    <div>
      <h2 className="font-heading text-lg font-bold mb-3">Pending Approvals</h2>
      <div className="space-y-2">
        {pending.map((r) => (
          <Card key={r.id} className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">
                {r.user_name} → {r.reward.icon} {r.reward.name}
              </div>
              <div className="text-xs text-forge-text-dim">
                {r.coin_cost_snapshot} coins • {formatDateTime(r.requested_at)}
              </div>
            </div>
            <ApprovalButtons onApprove={() => onApprove(r.id)} onReject={() => onReject(r.id)} />
          </Card>
        ))}
      </div>
    </div>
  );
}

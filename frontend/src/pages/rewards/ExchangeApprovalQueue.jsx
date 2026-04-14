import { ArrowRightLeft } from 'lucide-react';
import ApprovalQueue from '../../components/ApprovalQueue';
import Card from '../../components/Card';
import { formatCurrency, formatDateTime } from '../../utils/format';

export default function ExchangeApprovalQueue({ pending, onApprove, onReject }) {
  return (
    <ApprovalQueue
      items={pending}
      title="Pending Exchanges"
      icon={<ArrowRightLeft size={18} />}
      onApprove={onApprove}
      onReject={onReject}
    >
      {({ item: ex, actions }) => (
        <Card key={ex.id} className="flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">
              {ex.user_name} — {formatCurrency(ex.dollar_amount)} → {ex.coin_amount} coins
            </div>
            <div className="text-xs text-ink-whisper">
              Rate: {ex.exchange_rate} coins/$1 • {formatDateTime(ex.created_at)}
            </div>
          </div>
          {actions}
        </Card>
      )}
    </ApprovalQueue>
  );
}

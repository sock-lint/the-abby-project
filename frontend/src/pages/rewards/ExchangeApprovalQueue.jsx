import { ArrowRightLeft } from 'lucide-react';
import ApprovalButtons from '../../components/ApprovalButtons';
import Card from '../../components/Card';
import { formatCurrency, formatDateTime } from '../../utils/format';

export default function ExchangeApprovalQueue({ pending, onApprove, onReject }) {
  if (!pending.length) return null;
  return (
    <div>
      <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
        <ArrowRightLeft size={18} /> Pending Exchanges
      </h2>
      <div className="space-y-2">
        {pending.map((ex) => (
          <Card key={ex.id} className="flex items-center justify-between">
            <div>
              <div className="text-sm font-medium">
                {ex.user_name} — {formatCurrency(ex.dollar_amount)} → {ex.coin_amount} coins
              </div>
              <div className="text-xs text-forge-text-dim">
                Rate: {ex.exchange_rate} coins/$1 • {formatDateTime(ex.created_at)}
              </div>
            </div>
            <ApprovalButtons onApprove={() => onApprove(ex.id)} onReject={() => onReject(ex.id)} />
          </Card>
        ))}
      </div>
    </div>
  );
}

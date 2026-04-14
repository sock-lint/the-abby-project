import { ArrowRightLeft } from 'lucide-react';
import Card from '../../components/Card';
import { STATUS_COLORS } from '../../constants/colors';
import { formatCurrency, formatDate } from '../../utils/format';

export default function ExchangeHistory({ exchanges, isParent }) {
  if (!exchanges.length) return null;
  return (
    <div>
      <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
        <ArrowRightLeft size={18} /> {isParent ? 'All Exchanges' : 'My Exchanges'}
      </h2>
      <div className="space-y-2">
        {exchanges.map((ex) => (
          <Card key={ex.id} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-primary/20 flex items-center justify-center">
                <ArrowRightLeft size={14} className="text-amber-highlight" />
              </div>
              <div>
                <div className="text-sm font-medium">
                  {formatCurrency(ex.dollar_amount)} → {ex.coin_amount} coins
                </div>
                <div className="text-xs text-forge-text-dim">
                  {isParent && `${ex.user_name} • `}
                  {formatDate(ex.created_at)} • {ex.exchange_rate} coins/$1
                </div>
              </div>
            </div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[ex.status] || STATUS_COLORS.pending}`}>
              {ex.status}
            </span>
          </Card>
        ))}
      </div>
    </div>
  );
}

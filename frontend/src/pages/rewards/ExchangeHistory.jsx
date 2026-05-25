import { ArrowRightLeft } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { STATUS_COLORS } from '../../constants/colors';
import { formatCurrency, formatDate } from '../../utils/format';

export default function ExchangeHistory({ exchanges, isParent }) {
  if (!exchanges.length) return null;
  return (
    <div className="space-y-2">
      {exchanges.map((ex) => (
          <ParchmentCard key={ex.id} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-sheikah-teal/20 flex items-center justify-center">
                <ArrowRightLeft size={14} className="text-sheikah-teal-deep" />
              </div>
              <div>
                <div className="font-body text-body font-medium">
                  {formatCurrency(ex.dollar_amount)} → {ex.coin_amount} coins
                </div>
                <div className="font-script text-caption text-ink-whisper">
                  {isParent && `${ex.user_name} • `}
                  {formatDate(ex.created_at)} • {ex.exchange_rate} coins/$1
                </div>
              </div>
            </div>
            <span className={`text-micro px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[ex.status] || STATUS_COLORS.pending}`}>
              {ex.status}
            </span>
          </ParchmentCard>
        ))}
    </div>
  );
}

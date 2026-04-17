import { Clock } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { STATUS_COLORS } from '../../constants/colors';
import { formatDate } from '../../utils/format';

export default function RedemptionHistory({ redemptions, isParent }) {
  if (!redemptions.length) return null;
  return (
    <div>
      <h2 className="font-display text-lg font-bold mb-3 flex items-center gap-2">
        <Clock size={18} /> {isParent ? 'All Redemptions' : 'My Redemptions'}
      </h2>
      <div className="space-y-2">
        {redemptions.map((r) => (
          <ParchmentCard key={r.id} className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="text-xl">{r.reward.icon || '🎁'}</div>
              <div>
                <div className="text-sm font-medium">{r.reward.name}</div>
                <div className="text-xs text-ink-whisper">
                  {isParent && `${r.user_name} • `}
                  {formatDate(r.requested_at)} • {r.coin_cost_snapshot} coins
                </div>
              </div>
            </div>
            <span className={`text-micro px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[r.status] || STATUS_COLORS.pending}`}>
              {r.status}
            </span>
          </ParchmentCard>
        ))}
      </div>
    </div>
  );
}

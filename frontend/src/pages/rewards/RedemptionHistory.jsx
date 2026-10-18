import ParchmentCard from '../../components/journal/ParchmentCard';
import { STATUS_COLORS } from '../../constants/colors';
import { formatDate } from '../../utils/format';

export default function RedemptionHistory({ redemptions, isParent }) {
  if (!redemptions.length) return null;
  return (
    <div className="space-y-2">
      {redemptions.map((r) => (
          <ParchmentCard key={r.id} className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="text-xl shrink-0">{r.reward.icon || '🎁'}</div>
              <div className="min-w-0 break-words">
                <div className="font-body text-body font-medium">{r.reward.name}</div>
                <div className="font-script text-caption text-ink-whisper">
                  {isParent && `${r.user_name} • `}
                  {formatDate(r.requested_at)} • {r.coin_cost_snapshot} coins
                </div>
                {r.parent_notes && <p className="text-caption text-ink-secondary whitespace-pre-wrap">Parent note: {r.parent_notes}</p>}
                {r.delivered_at && <p className="text-caption text-ink-secondary">Delivered {formatDate(r.delivered_at)}</p>}
              </div>
            </div>
            <span className={`shrink-0 text-micro px-2 py-0.5 rounded-full border uppercase ${STATUS_COLORS[r.status] || STATUS_COLORS.pending}`}>
              {r.status === 'approved' ? 'Awaiting delivery' : r.status}
            </span>
          </ParchmentCard>
        ))}
    </div>
  );
}

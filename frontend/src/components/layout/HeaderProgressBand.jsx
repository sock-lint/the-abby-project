import { useNavigate } from 'react-router-dom';
import { getActiveQuest } from '../../api';
import { useApi } from '../../hooks/useApi';

/**
 * HeaderProgressBand — a soft quest-progress card under the header.
 * The quest name and percentage stay visible with a full mobile tap target.
 */
export default function HeaderProgressBand() {
  const navigate = useNavigate();
  const { data: activeQuest } = useApi(getActiveQuest);

  const isActive = activeQuest && activeQuest.status === 'active';
  const percent = isActive
    ? Math.max(0, Math.min(100, Number(activeQuest.progress_percent) || 0))
    : 0;
  const title = isActive ? activeQuest.definition?.name || 'Active quest' : '';

  if (!isActive) {
    return (
      <div
        aria-hidden="true"
        className="w-full"
        style={{ height: 1 }}
      />
    );
  }

  return (
    <div className="pb-3 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] lg:px-6">
      <button
        type="button"
        onClick={() => navigate('/trials')}
        aria-label={`${title} · ${percent}% complete`}
        title={`${title} · ${percent}%`}
        className="relative block w-full min-h-11 rounded-2xl border border-sheikah-teal/15 bg-ink-page-aged/80 px-3 py-2 text-left hover:bg-sheikah-teal/10 transition-colors"
      >
        <div className="relative w-full h-1.5 rounded-full bg-sheikah-teal/10 overflow-hidden" aria-hidden="true">
          <div
            className="absolute inset-y-0 left-0 rounded-full bg-sheikah-teal-deep transition-[width]"
            style={{ width: `${percent}%` }}
          />
        </div>
        <span
          className="flex items-center justify-between gap-2 pt-1.5 font-body font-semibold text-tiny text-ink-primary"
        >
          <span className="truncate">{title}</span>
          <span className="tabular-nums shrink-0">{percent}%</span>
        </span>
      </button>
    </div>
  );
}

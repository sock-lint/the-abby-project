import { useNavigate } from 'react-router-dom';
import { getActiveQuest } from '../../api';
import { useApi } from '../../hooks/useApi';

/**
 * HeaderProgressBand — thin full-width band under the header.
 *  - Inert hairline (page divider) when no quest is active.
 *  - Sheikah-teal gradient scaled to quest progress when one is active, tap
 *    routes to Quests page.
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
        className="w-full border-b border-ink-page-shadow/60"
        style={{ height: 1 }}
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => navigate('/quests')}
      aria-label={`${title} · ${percent}% complete`}
      title={`${title} · ${percent}%`}
      className="group relative w-full h-1 md:h-1.5 hover:h-2 transition-all bg-ink-page-shadow/50 focus:outline-none"
    >
      <div
        className="absolute inset-y-0 left-0 bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal animate-rune-pulse"
        style={{ width: `${percent}%` }}
      />
      {/* Tooltip shown on hover (desktop only-ish, safe to keep). */}
      <span
        className="pointer-events-none absolute top-full right-2 mt-0.5 hidden group-hover:block bg-ink-page-aged border border-ink-page-shadow rounded px-2 py-0.5 font-rune text-micro text-ink-secondary"
      >
        {title} · {percent}%
      </span>
    </button>
  );
}

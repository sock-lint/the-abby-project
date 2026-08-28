import { useNavigate } from 'react-router-dom';
import { getActiveQuest } from '../../api';
import { useApi } from '../../hooks/useApi';

/**
 * HeaderProgressBand — thin full-width band under the header.
 *  - Inert hairline (page divider) when no quest is active.
 *  - Sheikah-teal gradient scaled to quest progress when one is active, tap
 *    routes to the Trials page.
 *
 * When active the band is a real button, so it carries a real target: the
 * visual gradient stays a 4-6px hairline but the button is min-h-11 with
 * -my-2 pulling the extra height into the header's and the content well's
 * existing padding, so the layout doesn't move. The quest name + percent
 * render inline — they used to live in a `group-hover` tooltip, which no
 * touch device can ever show.
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
      onClick={() => navigate('/trials')}
      aria-label={`${title} · ${percent}% complete`}
      title={`${title} · ${percent}%`}
      className="relative block w-full min-h-11 -my-2 pt-2 text-left focus:outline-none"
    >
      <div className="relative w-full h-1 md:h-1.5 bg-ink-page-shadow/50">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal animate-rune-pulse"
          style={{ width: `${percent}%` }}
        />
      </div>
      <span
        className="flex items-center justify-between gap-2 pt-1
                   pl-[max(1rem,env(safe-area-inset-left))]
                   pr-[max(1rem,env(safe-area-inset-right))] lg:px-6
                   font-rune text-tiny text-ink-secondary"
      >
        <span className="truncate">{title}</span>
        <span className="tabular-nums shrink-0">{percent}%</span>
      </span>
    </button>
  );
}

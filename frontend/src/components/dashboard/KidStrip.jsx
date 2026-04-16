import ParchmentCard from '../journal/ParchmentCard';
import { Clock } from 'lucide-react';

/**
 * KidStrip — parent "Who's doing what" row list.
 *
 * Each row: avatar, name, activity status, optional earnings delta.
 * Per-kid earnings may not be in the current payload — when absent, we show
 * last-activity hint only.
 */
export default function KidStrip({ kids = [] }) {
  if (!kids || kids.length === 0) return null;
  return (
    <ParchmentCard>
      <div className="font-script text-sheikah-teal-deep text-xs uppercase tracking-wider mb-2">
        Who&apos;s on the page
      </div>
      <ul className="space-y-2">
        {kids.map((k) => {
          const initial = (k.display_name || k.username || '?')[0].toUpperCase();
          const clockedIn = k.active_timer || k.clocked_in_project;
          return (
            <li
              key={k.id}
              className="flex items-center gap-3 rounded-lg px-2 py-1.5 hover:bg-ink-page-rune-glow transition-colors"
            >
              <div className="w-9 h-9 rounded-full bg-sheikah-teal/15 border border-sheikah-teal/40 flex items-center justify-center font-display text-sheikah-teal-deep text-sm shrink-0">
                {initial}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-display text-base text-ink-primary truncate">
                  {k.display_name || k.username}
                </div>
                <div className="font-script text-xs text-ink-whisper truncate">
                  {clockedIn ? (
                    <span className="inline-flex items-center gap-1 text-sheikah-teal-deep">
                      <Clock size={11} />
                      Clocked in
                      {k.active_timer?.project_title && `: ${k.active_timer.project_title}`}
                    </span>
                  ) : k.last_activity_label ? (
                    k.last_activity_label
                  ) : (
                    'Quiet today'
                  )}
                </div>
              </div>
              {k.today_earnings != null && (
                <div className="font-rune text-xs text-ember-deep shrink-0">
                  ${Number(k.today_earnings).toFixed(2)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </ParchmentCard>
  );
}

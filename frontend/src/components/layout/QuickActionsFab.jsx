import { useEffect, useState } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Plus } from 'lucide-react';
import { getClockStatus } from '../../api';
import { useApi } from '../../hooks/useApi';
import { ClockFabIcon } from '../icons/JournalIcons';
import QuickActionsSheet from './QuickActionsSheet';

function formatElapsed(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (h === 0) {
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${h}:${m.toString().padStart(2, '0')}`;
}

/**
 * QuickActionsFab — replaces ClockFab. Same bottom-right position, but the
 * button now opens a contextual actions sheet. Still shows a running-timer
 * chip when clocked in so the at-a-glance signal is preserved.
 */
export default function QuickActionsFab() {
  const { data: status, reload: reloadStatus } = useApi(getClockStatus);
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const isClocked = status && status.status === 'active';
  const clockInAt = isClocked ? status?.clock_in : null;

  useEffect(() => {
    if (!clockInAt) return undefined;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [clockInAt]);

  const elapsedSecs = clockInAt
    ? Math.max(0, Math.floor((now - new Date(clockInAt).getTime()) / 1000))
    : 0;

  const label = isClocked ? formatElapsed(elapsedSecs) : 'Quick';

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={isClocked ? 'Quick actions (clocked in)' : 'Quick actions'}
        className={`fixed z-30 rounded-full shadow-xl transition-all
                    bottom-24 right-4 md:bottom-6 md:right-6
                    flex items-center gap-2 pl-3 pr-4 py-3
                    ${isClocked
                      ? 'bg-ember text-ink-page-rune-glow border border-ember-deep animate-rune-pulse'
                      : 'bg-sheikah-teal-deep text-ink-page-rune-glow border border-sheikah-teal-deep/60 hover:bg-sheikah-teal'
                    }`}
      >
        {isClocked ? <ClockFabIcon size={22} /> : <Plus size={22} />}
        <span className="font-rune text-sm font-bold tabular-nums">{label}</span>
      </button>

      <AnimatePresence>
        {open && (
          <QuickActionsSheet
            status={status}
            isClocked={isClocked}
            elapsedSecs={elapsedSecs}
            onClose={() => setOpen(false)}
            onClockReload={reloadStatus}
          />
        )}
      </AnimatePresence>
    </>
  );
}

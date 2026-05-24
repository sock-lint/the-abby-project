import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Plus } from 'lucide-react';
import { getClockStatus } from '../../api';
import { useApi } from '../../hooks/useApi';
import { ClockFabIcon } from '../icons/JournalIcons';
import QuickActionsSheet from './QuickActionsSheet';
import { STORAGE_KEYS } from '../../constants/storage';

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
  const [bouncing, setBouncing] = useState(false);

  const storedVal = localStorage.getItem(STORAGE_KEYS.FAB_ONBOARDED);
  const visitCount = storedVal === 'done' ? Infinity : Number(storedVal || '0');
  const [showHint, setShowHint] = useState(() => visitCount < 3);

  useEffect(() => {
    if (visitCount < 2) {
      setBouncing(true);
      const timer = setTimeout(() => setBouncing(false), 2000);
      return () => clearTimeout(timer);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

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

  const label = isClocked ? formatElapsed(elapsedSecs) : null;

  const handleOpen = () => {
    setOpen(true);
    if (showHint) {
      setShowHint(false);
      localStorage.setItem(STORAGE_KEYS.FAB_ONBOARDED, 'done');
    }
  };

  useEffect(() => {
    if (!showHint) return undefined;
    const timer = setTimeout(() => {
      setShowHint(false);
      const cur = localStorage.getItem(STORAGE_KEYS.FAB_ONBOARDED);
      if (cur !== 'done') {
        localStorage.setItem(STORAGE_KEYS.FAB_ONBOARDED, String(Number(cur || '0') + 1));
      }
    }, 8000);
    return () => clearTimeout(timer);
  }, [showHint]);

  return (
    <>
      {showHint && !isClocked && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          className="fixed z-30 bottom-40 right-4 lg:bottom-20 lg:right-6
                     bg-ink-page-aged border border-sheikah-teal/40 rounded-lg
                     px-3 py-2 shadow-lg max-w-[160px]"
        >
          <p className="font-script text-caption text-sheikah-teal-deep text-center">
            Tap for quick actions
          </p>
          <div
            className="absolute -bottom-1.5 right-6 w-3 h-3 bg-ink-page-aged
                       border-b border-r border-sheikah-teal/40 rotate-45"
            aria-hidden="true"
          />
        </motion.div>
      )}

      <button
        type="button"
        onClick={handleOpen}
        aria-label={isClocked ? 'Quick actions (clocked in)' : 'Quick actions'}
        className={`fixed z-30 rounded-full shadow-xl transition-all
                    bottom-24 right-4 lg:bottom-6 lg:right-6
                    flex items-center gap-2 ${isClocked ? 'pl-3 pr-4' : 'p-3.5'} py-3
                    ${bouncing ? 'animate-bounce' : ''}
                    ${isClocked
                      ? 'bg-ember text-ink-page-rune-glow border border-ember-deep animate-rune-pulse'
                      : 'bg-sheikah-teal-deep text-ink-page-rune-glow border border-sheikah-teal-deep/60 hover:bg-sheikah-teal'
                    }`}
      >
        {isClocked ? <ClockFabIcon size={22} /> : <Plus size={22} />}
        {label && <span className="font-rune text-sm font-bold tabular-nums">{label}</span>}
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

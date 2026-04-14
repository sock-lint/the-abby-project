import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { NavLink } from 'react-router-dom';
import { Play, Square, X } from 'lucide-react';
import { getClockStatus, clockIn, clockOut, getProjects } from '../../api';
import { useApi } from '../../hooks/useApi';
import { normalizeList } from '../../utils/api';
import { ClockFabIcon } from '../icons/JournalIcons';
import ParchmentCard from '../journal/ParchmentCard';
import { buttonPrimary, buttonDanger, inputClass } from '../../constants/styles';

/**
 * ClockFab — persistent floating rune button anchored bottom-right. Visible
 * on every page. Opens a compact clock-in/out modal instead of taking the
 * user to a dedicated page. A link to the full `/clock` log lives inside
 * the modal for history access.
 */
export default function ClockFab() {
  const { data: status, reload: reloadStatus } = useApi(getClockStatus);
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const isClocked = status && status.status === 'active';
  const clockInAt = isClocked ? status?.clock_in : null;

  // Live tick while clocked in — drives a "now" cursor from which elapsed
  // is derived. Deriving instead of storing elapsed avoids setState-inside-
  // effect cascades flagged by react-hooks/set-state-in-effect.
  useEffect(() => {
    if (!clockInAt) return undefined;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [clockInAt]);

  const elapsed = clockInAt
    ? Math.max(0, Math.floor((now - new Date(clockInAt).getTime()) / 1000))
    : 0;

  const fabLabel = isClocked ? formatElapsed(elapsed, true) : 'Clock';

  return (
    <>
      {/* Floating action button */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={isClocked ? 'Clock out' : 'Clock in'}
        className={`fixed z-20 rounded-full shadow-xl transition-all
                    bottom-24 right-4 md:bottom-6 md:right-6
                    flex items-center gap-2 pl-3 pr-4 py-3
                    ${isClocked
                      ? 'bg-ember text-ink-page-rune-glow border border-ember-deep animate-rune-pulse'
                      : 'bg-sheikah-teal-deep text-ink-page-rune-glow border border-sheikah-teal-deep/60 hover:bg-sheikah-teal'
                    }`}
      >
        <ClockFabIcon size={22} />
        <span className="font-rune text-sm font-bold tabular-nums">{fabLabel}</span>
      </button>

      <AnimatePresence>
        {open && (
          <ClockModal
            status={status}
            elapsed={elapsed}
            isClocked={isClocked}
            onClose={() => setOpen(false)}
            onReload={reloadStatus}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function ClockModal({ status, elapsed, isClocked, onClose, onReload }) {
  const { data: projectsData } = useApi(getProjects);
  const projects = normalizeList(projectsData);
  const [selectedProject, setSelectedProject] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleClockIn = async () => {
    if (!selectedProject) {
      setError('Select a venture first');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await clockIn(parseInt(selectedProject));
      await onReload();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleClockOut = async () => {
    setBusy(true);
    setError('');
    try {
      await clockOut(notes);
      await onReload();
      setNotes('');
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.18 }}
        onClick={onClose}
        className="fixed inset-0 z-30 bg-ink-primary/40 backdrop-blur-sm"
      />
      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.96 }}
        transition={{ type: 'spring', damping: 28, stiffness: 320 }}
        className="fixed inset-x-4 bottom-20 md:inset-auto md:bottom-20 md:right-6 md:w-96 z-40"
        role="dialog"
        aria-label="Clock in and out"
      >
        <ParchmentCard flourish tone="bright" className="shadow-2xl">
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="absolute top-2 right-2 p-1 rounded-full hover:bg-ink-page-shadow/50 transition-colors"
          >
            <X size={16} className="text-ink-secondary" />
          </button>

          <div className="font-script text-ink-whisper text-xs uppercase tracking-wider">
            {isClocked ? 'time still inking' : 'open a new entry'}
          </div>

          {isClocked ? (
            <>
              <div className="font-display text-lg text-ink-primary mt-1 truncate">
                {status?.project_title}
              </div>
              <div className="font-rune text-4xl font-bold text-ember-deep tabular-nums my-3 text-center">
                {formatElapsed(elapsed)}
              </div>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Scribble what you did…"
                className={`${inputClass} resize-none h-20 mb-3`}
              />
              {error && (
                <div className="text-ember-deep text-sm mb-2 font-script">{error}</div>
              )}
              <div className="flex gap-2">
                <button
                  onClick={handleClockOut}
                  disabled={busy}
                  className={`${buttonDanger} flex-1 px-4 py-2.5 flex items-center justify-center gap-2`}
                >
                  <Square size={18} />
                  Clock Out
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="mt-2 mb-3">
                <label
                  className="block font-script text-sm text-ink-secondary mb-1"
                  htmlFor="clockfab-project"
                >
                  Which venture?
                </label>
                <select
                  id="clockfab-project"
                  value={selectedProject}
                  onChange={(e) => setSelectedProject(e.target.value)}
                  className={inputClass}
                >
                  <option value="">Select a project…</option>
                  {projects
                    .filter((p) => ['active', 'in_progress'].includes(p.status))
                    .map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.title}
                      </option>
                    ))}
                </select>
              </div>
              {error && (
                <div className="text-ember-deep text-sm mb-2 font-script">{error}</div>
              )}
              <button
                onClick={handleClockIn}
                disabled={busy}
                className={`${buttonPrimary} w-full px-4 py-2.5 flex items-center justify-center gap-2`}
              >
                <Play size={18} />
                Clock In
              </button>
            </>
          )}

          <div className="mt-3 pt-3 border-t border-ink-page-shadow/70 text-center">
            <NavLink
              to="/clock"
              onClick={onClose}
              className="font-script text-sm text-sheikah-teal-deep hover:underline"
            >
              See the full expedition log →
            </NavLink>
          </div>
        </ParchmentCard>
      </motion.div>
    </>
  );
}

function formatElapsed(secs, compact = false) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  if (compact && h === 0) {
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

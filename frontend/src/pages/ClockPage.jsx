import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Square, Ban } from 'lucide-react';
import { getClockStatus, clockIn, clockOut, getProjects, getTimeEntries, voidTimeEntry } from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import ConfirmDialog from '../components/ConfirmDialog';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import IconButton from '../components/IconButton';
import { ClockFabIcon, InkwellIcon } from '../components/icons/JournalIcons';
import { SelectField, TextAreaField } from '../components/form';
import { formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';

export default function ClockPage() {
  const { isParent } = useRole();
  const { data: status, reload: reloadStatus } = useApi(getClockStatus);
  const { data: projectsData } = useApi(getProjects);
  const { data: entriesData, reload: reloadEntries } = useApi(getTimeEntries);
  const [selectedProject, setSelectedProject] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const [voidEntryId, setVoidEntryId] = useState(null);

  const projects = normalizeList(projectsData);
  const entries = normalizeList(entriesData);
  const isClocked = status && status.status === 'active';
  const clockInAt = isClocked ? status?.clock_in : null;

  useEffect(() => {
    if (!clockInAt) return undefined;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [clockInAt]);

  const elapsed = clockInAt
    ? Math.max(0, Math.floor((now - new Date(clockInAt).getTime()) / 1000))
    : 0;

  const formatTime = (secs) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleClockIn = async () => {
    setError('');
    if (!selectedProject) { setError('Select a venture first'); return; }
    try {
      await clockIn(parseInt(selectedProject));
      reloadStatus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleClockOut = async () => {
    setError('');
    try {
      await clockOut(notes);
      setNotes('');
      reloadStatus();
      reloadEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  const confirmVoid = async () => {
    const entryId = voidEntryId;
    setVoidEntryId(null);
    try {
      await voidTimeEntry(entryId);
      reloadEntries();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <header className="text-center">
        <div className="font-script text-sheikah-teal-deep text-base">
          the expedition log
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Clock
        </h1>
        <div className="font-script text-body text-ink-whisper mt-1">
          each hour at a venture inks coins, XP, and weekly wages
        </div>
      </header>

      {/* Timer Display */}
      <motion.div layout>
        <ParchmentCard
          flourish
          tone={isClocked ? 'bright' : 'default'}
          className={`text-center py-8 ${isClocked ? 'border-ember/60' : ''}`}
        >
          <AnimatePresence mode="wait">
            {isClocked ? (
              <motion.div key="active" initial={{ scale: 0.85 }} animate={{ scale: 1 }}>
                <div className="font-script text-sheikah-teal-deep text-body uppercase tracking-widest mb-1">
                  now inking
                </div>
                <div className="font-display text-lg text-ink-primary mb-3">
                  {status.project_title}
                </div>
                <div className="font-rune text-5xl md:text-6xl font-bold text-ember-deep mb-6 tabular-nums">
                  {formatTime(elapsed)}
                </div>
                <div className="mb-4">
                  <TextAreaField
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                    placeholder="Scribble what you did…"
                    inputMode="text"
                    rows={3}
                  />
                </div>
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.95 }}
                  onClick={handleClockOut}
                  className="w-28 h-28 mx-auto rounded-full bg-ember-deep hover:bg-ember flex items-center justify-center text-ink-page-rune-glow shadow-xl shadow-ember-deep/25 transition-colors border-2 border-ember"
                >
                  <Square size={36} />
                </motion.button>
                <div className="font-script text-body text-ink-whisper mt-3">
                  tap to close the entry · the hour rolls into your weekly wages
                </div>
              </motion.div>
            ) : (
              <motion.div key="idle" initial={{ scale: 0.85 }} animate={{ scale: 1 }}>
                <ClockFabIcon size={36} className="text-ink-whisper mx-auto mb-3" />
                <div className="font-rune text-5xl md:text-6xl font-bold text-ink-whisper mb-6 tabular-nums">
                  00:00:00
                </div>
                <div className="mb-4">
                  <SelectField
                    value={selectedProject}
                    onChange={(e) => setSelectedProject(e.target.value)}
                  >
                    <option value="">Select a venture…</option>
                    {projects.filter((p) => ['active', 'in_progress'].includes(p.status)).map((p) => (
                      <option key={p.id} value={p.id}>{p.title}</option>
                    ))}
                  </SelectField>
                </div>
                <motion.button
                  type="button"
                  whileTap={{ scale: 0.95 }}
                  onClick={handleClockIn}
                  className="w-28 h-28 mx-auto rounded-full bg-moss hover:bg-moss/90 flex items-center justify-center text-ink-page-rune-glow shadow-xl shadow-moss/25 transition-colors border-2 border-moss/80"
                >
                  <Play size={36} className="ml-1" />
                </motion.button>
                <div className="font-script text-body text-ink-whisper mt-3">
                  tap to begin inking · earns coins and XP per hour
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </ParchmentCard>
      </motion.div>

      <ErrorAlert message={error} />

      {/* Recent entries */}
      {entries.length > 0 && (
        <section>
          <h2 className="font-display text-xl text-ink-primary leading-tight mb-3">
            Recent entries
          </h2>
          <div className="space-y-2">
            {entries.slice(0, 10).map((e) => (
              <ParchmentCard
                key={e.id}
                className={`flex items-center justify-between gap-3 py-3 ${e.status === 'voided' ? 'opacity-50' : ''}`}
              >
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <InkwellIcon size={16} className="text-ink-secondary shrink-0" />
                  <div className="min-w-0">
                    <div
                      className={`font-body text-body font-medium text-ink-primary truncate ${e.status === 'voided' ? 'line-through' : ''}`}
                    >
                      {e.project_title}
                    </div>
                    <div className="font-script text-caption text-ink-whisper truncate">
                      {formatDate(e.clock_in)} {e.notes && `· ${e.notes}`}
                      {e.status === 'voided' && (
                        <span className="text-ember-deep ml-1">(voided)</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="font-rune font-bold text-body text-ink-primary tabular-nums">
                    {e.duration_minutes ? formatDuration(e.duration_minutes) : '…'}
                  </span>
                  {isParent && e.status !== 'voided' && e.status !== 'active' && (
                    <IconButton
                      size="sm"
                      onClick={() => setVoidEntryId(e.id)}
                      title="Void entry"
                      aria-label="Void entry"
                      className="hover:text-ember-deep"
                    >
                      <Ban size={14} />
                    </IconButton>
                  )}
                </div>
              </ParchmentCard>
            ))}
          </div>
        </section>
      )}

      {entries.length === 0 && (
        <RuneBadge tone="ink" size="md" className="mx-auto">
          no entries yet — clock in to begin the log · each hour earns coin, XP, and a weekly wage
        </RuneBadge>
      )}

      {voidEntryId && (
        <ConfirmDialog
          title="Void this time entry?"
          message="This cannot be undone."
          confirmLabel="Void"
          onConfirm={confirmVoid}
          onCancel={() => setVoidEntryId(null)}
        />
      )}
    </div>
  );
}

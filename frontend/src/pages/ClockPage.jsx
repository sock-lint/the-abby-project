import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Play, Square, Ban } from 'lucide-react';
import { getClockStatus, clockIn, clockOut, getProjects, getTimeEntries, voidTimeEntry } from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import ConfirmDialog from '../components/ConfirmDialog';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentCard from '../components/journal/ParchmentCard';
import ParchmentSkeleton from '../components/ParchmentSkeleton';
import PageShell from '../components/layout/PageShell';
import PageHeader from '../components/layout/PageHeader';
import IconButton from '../components/IconButton';
import { ClockFabIcon, InkwellIcon } from '../components/icons/JournalIcons';
import { SelectField, TextAreaField } from '../components/form';
import { formatDate, formatDuration } from '../utils/format';
import { normalizeList } from '../utils/api';
import { activeProjectsOf, defaultClockProjectId, rememberClockProject } from '../utils/clock';

// Below this elapsed-seconds threshold a clock-out is almost certainly an
// "oh wait I just started" misclick recovery — letting the confirm fire
// would be more annoying than the rare benefit of catching it. Above the
// threshold, the user has real wages on the line and the confirm dialog
// is the asymmetric-safety net (compare to "void entry" which gates
// behind ConfirmDialog despite being reversible).
const CLOCK_OUT_CONFIRM_THRESHOLD_SECONDS = 60;

export default function ClockPage() {
  const { isParent } = useRole();
  const {
    data: status, loading: loadingStatus, refreshing: refreshingStatus,
    error: statusError, reload: reloadStatus,
  } = useApi(getClockStatus);
  const {
    data: projectsData, loading: loadingProjects, refreshing: refreshingProjects,
    error: projectsError, reload: reloadProjects,
  } = useApi(getProjects);
  const {
    data: entriesData, loading: loadingEntries,
    error: entriesError, reload: reloadEntries,
  } = useApi(getTimeEntries);
  // null = untouched (falls back to the remembered/default venture); a real
  // selection — including explicitly clearing to '' — always wins.
  const [selectedProject, setSelectedProject] = useState(null);
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [now, setNow] = useState(() => Date.now());
  const [voidEntryId, setVoidEntryId] = useState(null);
  const [confirmingClockOut, setConfirmingClockOut] = useState(false);
  // The 112px seals are the easiest thing on the page to double-tap on a
  // slow connection; without this a second tap fires clockIn/clockOut again.
  const [clockBusy, setClockBusy] = useState(false);

  const projects = normalizeList(projectsData);
  const entries = normalizeList(entriesData);
  const isClocked = status && status.status === 'active';
  const clockInAt = isClocked ? status?.clock_in : null;
  const statusReady = Boolean(status) && !loadingStatus && !refreshingStatus && !statusError;
  const projectsReady = !loadingProjects && !refreshingProjects && !projectsError;

  // Preselect the remembered venture (or the only active one) so the daily
  // repeat case is a single tap on the Play seal instead of a picker session.
  const activeProjects = activeProjectsOf(projects);
  const effectiveProject = selectedProject ?? defaultClockProjectId(activeProjects);

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
    if (clockBusy || !statusReady || !projectsReady) return;
    if (!effectiveProject) { setError('Select a project first'); return; }
    setClockBusy(true);
    try {
      await clockIn(parseInt(effectiveProject));
      rememberClockProject(effectiveProject);
      await reloadStatus();
    } catch (err) {
      setError(err.message);
    } finally {
      setClockBusy(false);
    }
  };

  const performClockOut = async () => {
    setError('');
    if (clockBusy || !statusReady) return;
    setClockBusy(true);
    try {
      await clockOut(notes);
      setNotes('');
      await Promise.all([reloadStatus(), reloadEntries()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setClockBusy(false);
    }
  };

  const handleClockOut = () => {
    if (clockBusy || !statusReady) return;
    if (elapsed >= CLOCK_OUT_CONFIRM_THRESHOLD_SECONDS) {
      setConfirmingClockOut(true);
      return;
    }
    performClockOut();
  };

  const confirmClockOut = () => {
    setConfirmingClockOut(false);
    performClockOut();
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
    <PageShell width="narrow" rhythm="loose">
      <div>
        <PageHeader title="Time tracking" kicker="Track your project work" />
        <p className="font-body text-body text-ink-secondary mt-1">
          Log project time to earn coins, XP, and weekly pay.
        </p>
      </div>

      <ErrorAlert
        message={statusError ? `Couldn't check your clock. ${statusError}` : null}
        onRetry={reloadStatus}
      />
      <ErrorAlert
        message={projectsError ? `Couldn't load projects. ${projectsError}` : null}
        onRetry={reloadProjects}
      />

      {/* Timer Display — held behind a skeleton until getClockStatus lands.
          Painting the idle 00:00:00 + Play seal first meant a kid who WAS
          clocked in saw (and could tap) the wrong control. */}
      {loadingStatus ? (
        <ParchmentSkeleton variant="hero" />
      ) : status && !statusError ? (
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
                    Clocked in
                  </div>
                  <div className="font-display text-lg text-ink-primary mb-3">
                    {status.project_title}
                  </div>
                  <div className="font-rune text-5xl md:text-6xl font-bold text-ember-deep mb-6 tabular-nums">
                    {formatTime(elapsed)}
                  </div>
                  <div className="mb-4">
                    <TextAreaField
                      label="Session notes"
                      value={notes}
                      onChange={(e) => setNotes(e.target.value)}
                      placeholder="Describe what you worked on…"
                      inputMode="text"
                      rows={3}
                    />
                  </div>
                  <motion.button
                    type="button"
                    whileTap={{ scale: 0.95 }}
                    onClick={handleClockOut}
                    disabled={clockBusy || !statusReady}
                    aria-label="Clock out"
                    aria-busy={clockBusy}
                    className="w-28 h-28 mx-auto rounded-full bg-ember-deep hover:bg-ember disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center text-ink-page-rune-glow shadow-xl shadow-ember-deep/25 transition-colors border-2 border-ember"
                  >
                    <Square size={36} />
                  </motion.button>
                  <div className="font-script text-body text-ink-whisper mt-3">
                    {clockBusy
                      ? 'Clocking out…'
                      : 'Clock out to save this session to your weekly timecard.'}
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
                      label="Project"
                      value={effectiveProject}
                      onChange={(e) => setSelectedProject(e.target.value)}
                      disabled={!projectsReady}
                    >
                      <option value="">Select a project…</option>
                      {activeProjects.map((p) => (
                        <option key={p.id} value={p.id}>{p.title}</option>
                      ))}
                    </SelectField>
                  </div>
                  <motion.button
                    type="button"
                    whileTap={{ scale: 0.95 }}
                    onClick={handleClockIn}
                    disabled={clockBusy || !statusReady || !projectsReady}
                    aria-label="Clock in"
                    aria-busy={clockBusy}
                    className="w-28 h-28 mx-auto rounded-full bg-moss hover:bg-moss/90 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center text-ink-page-rune-glow shadow-xl shadow-moss/25 transition-colors border-2 border-moss/80"
                  >
                    <Play size={36} className="ml-1" />
                  </motion.button>
                  <div className="font-script text-body text-ink-whisper mt-3">
                    {clockBusy
                      ? 'Clocking in…'
                      : 'Clock in to start tracking your work.'}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </ParchmentCard>
        </motion.div>
      ) : null}

      <ErrorAlert message={error} />

      {/* Recent entries */}
      <ErrorAlert
        message={entriesError ? `Couldn't load recent entries. ${entriesError}` : null}
        onRetry={reloadEntries}
      />
      {loadingEntries && <ParchmentSkeleton variant="list" count={3} />}

      {!loadingEntries && entries.length > 0 && (
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

      {/* Gated on its own loading flag — this used to flash on every visit
          while the entries request was still in flight. */}
      {!loadingEntries && !entriesError && entries.length === 0 && (
        <EmptyState icon={<ClockFabIcon size={36} />}>
          No time entries yet. Choose a project and clock in to start tracking your work.
        </EmptyState>
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

      {confirmingClockOut && (
        <ConfirmDialog
          title={`Clock out after ${formatTime(elapsed)}?`}
          message="This saves your session to your weekly timecard. Only a parent can void the entry afterward."
          confirmLabel="Clock out"
          onConfirm={confirmClockOut}
          onCancel={() => setConfirmingClockOut(false)}
        />
      )}
    </PageShell>
  );
}

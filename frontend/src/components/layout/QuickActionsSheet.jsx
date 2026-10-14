import { useContext, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Square, BookOpen, Box, Target, UserCog, PenTool, Palette, Sparkles, Feather, Activity } from 'lucide-react';
import { CoinIcon } from '../icons/JournalIcons';
import BottomSheet from '../BottomSheet';
import ConfirmDialog from '../ConfirmDialog';
import {
  clockIn, clockOut, getProjects,
  getHomeworkDashboard,
  getSavingsGoals,
  getTodayJournal,
} from '../../api';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import { normalizeList } from '../../utils/api';
import {
  activeProjectsOf,
  defaultClockProjectId,
  rememberClockProject,
  rememberedClockProject,
} from '../../utils/clock';
import Button from '../Button';
import { SelectField, TextAreaField } from '../form';
import JournalEntryFormModal from '../../pages/yearbook/JournalEntryFormModal';
import GradeEntryFormModal from '../../pages/grades/GradeEntryFormModal';
import CreationLogModal from '../CreationLogModal';
import MovementSessionLogModal from '../MovementSessionLogModal';
import HomeworkFormModal from '../../pages/Homework/HomeworkFormModal';
import HomeworkSubmitSheet from '../HomeworkSubmitSheet';
import { SuccessToastContext } from '../../contexts/SuccessToastContext';
import { formatDuration } from '../../utils/format';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';

function formatClock(secs) {
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function ActionRow({ icon, label, hint, onClick, tone = 'ink', disabled = false }) {
  const toneText = {
    ink: 'text-ink-primary',
    teal: 'text-sheikah-teal-deep',
    ember: 'text-ember-deep',
    moss: 'text-moss',
    gold: 'text-gold-leaf',
    royal: 'text-royal',
  }[tone];
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="w-full min-h-14 flex items-center gap-3 px-3 py-2.5 rounded-2xl border border-ink-page-shadow/60 bg-ink-page hover:bg-sheikah-teal/5 transition-colors disabled:opacity-50 text-left"
    >
      <span className={`${toneText} size-9 flex items-center justify-center rounded-xl bg-ink-page-aged shrink-0`}>{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block font-body text-body font-semibold text-ink-primary">
          {label}
        </span>
        {hint && (
          <span className="block font-body text-caption text-ink-whisper truncate">{hint}</span>
        )}
      </span>
    </button>
  );
}

function ClockPane({ status, isClocked, elapsedSecs, projects, onBack, onClockReload, notes, setNotes, busy, setBusy }) {
  // null = untouched — falls back to the remembered/default venture below.
  const [selectedProject, setSelectedProject] = useState(null);
  const [error, setError] = useState('');
  const [confirmingBack, setConfirmingBack] = useState(false);
  // Optional: App mounts SuccessToastProvider around the whole authed tree,
  // but the sheet is also rendered on its own in tests.
  const showSuccess = useContext(SuccessToastContext);

  const activeProjects = activeProjectsOf(projects);
  const effectiveProject = selectedProject ?? defaultClockProjectId(activeProjects);

  const handleIn = async () => {
    if (!effectiveProject) { setError('Select a project first'); return; }
    setBusy(true); setError('');
    try {
      await clockIn(parseInt(effectiveProject, 10));
      rememberClockProject(effectiveProject);
      await onClockReload();
      const started = activeProjects.find((p) => String(p.id) === String(effectiveProject));
      showSuccess?.(started ? `Clocked in · ${started.title}` : 'Clocked in');
      onBack();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const handleOut = async () => {
    setBusy(true); setError('');
    try {
      await clockOut(notes);
      await onClockReload();
      setNotes('');
      // The elapsed readout disappears with the sheet, so say what landed.
      showSuccess?.(`Clocked out · ${formatDuration(Math.round(elapsedSecs / 60))} logged`);
      onBack();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <button type="button" disabled={busy} onClick={() => notes ? setConfirmingBack(true) : onBack()} className="min-h-11 px-3 rounded-full font-body font-semibold text-body text-ink-primary hover:bg-sheikah-teal/10 disabled:opacity-50">
        ← Back
      </button>
      {isClocked ? (
        <>
          <div className="font-body text-ink-whisper text-caption uppercase tracking-wider">Time in progress</div>
          <div className="font-body text-lg truncate">{status?.project_title}</div>
          <div className="font-body text-3xl font-bold text-ember-deep tabular-nums text-center">
            {formatClock(elapsedSecs)}
          </div>
          <TextAreaField
            label="Clock-out notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Scribble what you did…"
            rows={3}
          />
          {error && <div className="text-ember-deep text-body font-body">{error}</div>}
          <Button
            variant="danger"
            onClick={handleOut}
            disabled={busy}
            className="w-full flex items-center justify-center gap-2"
          >
            <Square size={18} /> Clock out
          </Button>
        </>
      ) : (
        <>
          <SelectField
            id="qa-clock-project"
            label="Which project?"
            value={effectiveProject}
            onChange={(e) => setSelectedProject(e.target.value)}
          >
            <option value="">Select a project…</option>
            {activeProjects.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </SelectField>
          {error && <div className="text-ember-deep text-body font-body">{error}</div>}
          <Button
            onClick={handleIn}
            disabled={busy}
            className="w-full flex items-center justify-center gap-2"
          >
            <Play size={18} /> Clock in
          </Button>
        </>
      )}
      {confirmingBack && <ConfirmDialog
        stacked
        title="Discard clock-out notes?"
        message="Your notes have not been saved."
        confirmLabel="Discard"
        onCancel={() => setConfirmingBack(false)}
        onConfirm={() => { setNotes(''); onBack(); }}
      />}
    </div>
  );
}

/**
 * QuickActionsSheet — contextual action launcher shown by QuickActionsFab.
 * Role-aware and hide rules:
 *   - Child: Clock, Add homework, Submit homework (only if due),
 *            Ask for a print, Start quest (only if scroll in inventory),
 *            Request reward, Contribute to savings goal (only if goals exist).
 *   - Parent: Clock (rare), Assign homework, Adjust coins, Adjust payment.
 *
 * Copy convention: use the same plain-language feature names as navigation.
 * Labels are sentence case, here
 * and on the clock pane's buttons.
 */
export default function QuickActionsSheet({
  status, isClocked, elapsedSecs, onClose, onClockReload,
}) {
  const navigate = useNavigate();
  const { isParent } = useRole();
  const [pane, setPane] = useState('menu'); // 'menu' | 'clock'
  const [clockNotes, setClockNotes] = useState('');
  const [clockBusy, setClockBusy] = useState(false);
  const [journalOpen, setJournalOpen] = useState(false);
  const [gradeOpen, setGradeOpen] = useState(false);
  const [creationOpen, setCreationOpen] = useState(false);
  const [movementOpen, setMovementOpen] = useState(false);
  const [homeworkOpen, setHomeworkOpen] = useState(false);
  // The assignment being turned in, or null. Opening the submit sheet right
  // here mirrors the other rows (creation / movement / journal / add study)
  // and replaces a `?submit=<id>` deep link that the Study tab never read.
  const [submitAssignment, setSubmitAssignment] = useState(null);
  // Optional — see ClockPane.
  const showSuccess = useContext(SuccessToastContext);
  // Child only: today's journal entry (if already written). Drives the row
  // label + whether the modal opens in edit or create mode.
  const { data: todayJournal } = useApi(
    isParent ? () => Promise.resolve(null) : getTodayJournal,
  );
  const [journalMode, setJournalMode] = useState('create');
  const [journalEntry, setJournalEntry] = useState(null);

  const openJournal = () => {
    if (todayJournal && todayJournal.id) {
      setJournalEntry(todayJournal);
      setJournalMode('edit');
    } else {
      setJournalEntry(null);
      setJournalMode('create');
    }
    setJournalOpen(true);
  };

  // Contextual enable/disable flags.
  const { data: hwDashboard } = useApi(isParent ? () => Promise.resolve(null) : getHomeworkDashboard);
  const { data: goalsData } = useApi(isParent ? () => Promise.resolve([]) : getSavingsGoals);

  // Projects load at the sheet level (shared with ClockPane) so the menu can
  // upgrade "Clock in" to a one-tap row for the remembered venture — clock-in
  // is the most-repeated action in the app and used to cost five interactions.
  const { data: projectsData } = useApi(getProjects);
  const projects = normalizeList(projectsData);
  const quickClockProject = isClocked ? null : rememberedClockProject(activeProjectsOf(projects));
  const [quickClockBusy, setQuickClockBusy] = useState(false);
  const dirty = Boolean(clockNotes);
  const busy = clockBusy || quickClockBusy;
  usePwaUpdateGuard(dirty || busy);

  const handleQuickClockIn = async () => {
    setQuickClockBusy(true);
    try {
      await clockIn(quickClockProject.id);
      rememberClockProject(quickClockProject.id);
      await onClockReload();
      showSuccess?.(`Clocked in · ${quickClockProject.title}`);
      onClose();
    } catch {
      // Whatever went wrong (project archived, already clocked in…), the
      // full pane has the picker and shows the real error on retry.
      setPane('clock');
    } finally {
      setQuickClockBusy(false);
    }
  };

  const hasDueHw = !isParent && (
    normalizeList(hwDashboard?.today).length > 0 ||
    normalizeList(hwDashboard?.overdue).length > 0
  );
  const firstDueHw = hasDueHw
    ? normalizeList(hwDashboard.overdue)[0] || normalizeList(hwDashboard.today)[0]
    : null;
  const hasGoals = !isParent && normalizeList(goalsData).some((g) => !g.is_completed);

  return (
    <>
    {gradeOpen && (
      <GradeEntryFormModal
        onClose={() => setGradeOpen(false)}
        onSaved={(entry) => {
          setGradeOpen(false);
          onClose();
          navigate('/chronicle?tab=grades', { state: { gradeSavedId: entry.id } });
        }}
      />
    )}
    {journalOpen && (
      <JournalEntryFormModal
        mode={journalMode}
        entry={journalEntry}
        onClose={() => setJournalOpen(false)}
        onSaved={() => {
          setJournalOpen(false);
          onClose();
        }}
      />
    )}
    {creationOpen && (
      <CreationLogModal
        onClose={() => setCreationOpen(false)}
        onSaved={() => {
          setCreationOpen(false);
          onClose();
        }}
      />
    )}
    {movementOpen && (
      <MovementSessionLogModal
        onClose={() => setMovementOpen(false)}
        onSaved={() => {
          setMovementOpen(false);
          onClose();
        }}
      />
    )}
    {homeworkOpen && (
      <HomeworkFormModal
        isParent={false}
        onClose={() => setHomeworkOpen(false)}
        onSaved={() => {
          setHomeworkOpen(false);
          onClose();
        }}
      />
    )}
    <HomeworkSubmitSheet
      assignment={submitAssignment}
      onClose={() => setSubmitAssignment(null)}
      onSubmitted={() => {
        setSubmitAssignment(null);
        showSuccess?.('Turned in — waiting on a parent');
        onClose();
      }}
    />

    <BottomSheet title={pane === 'menu' ? 'Quick actions' : 'Clock'} onClose={onClose} dirty={dirty} disabled={busy}>
      {pane === 'menu' && (
        <div className="space-y-2">
          {quickClockProject ? (
            <>
              <ActionRow
                icon={<Play size={18} />}
                label={quickClockBusy ? 'Clocking in…' : `Clock in · ${quickClockProject.title}`}
                hint="One tap — starts the timer"
                tone="teal"
                disabled={quickClockBusy}
                onClick={handleQuickClockIn}
              />
              <button
                type="button"
                onClick={() => setPane('clock')}
                className="block w-full min-h-11 text-left px-3 py-2 rounded-xl font-body text-caption text-ink-primary hover:bg-sheikah-teal/10"
              >
                Choose a different project →
              </button>
            </>
          ) : (
            <ActionRow
              icon={isClocked ? <Square size={18} /> : <Play size={18} />}
              label={isClocked ? 'Stop clock' : 'Clock in'}
              hint={isClocked ? status?.project_title : 'Open an entry'}
              tone={isClocked ? 'ember' : 'teal'}
              onClick={() => setPane('clock')}
            />
          )}

          {!isParent && (
            <>
              <ActionRow
                icon={<Palette size={18} />}
                label="Log a creation"
                hint="Photo of something you made"
                tone="gold"
                onClick={() => setCreationOpen(true)}
              />
              <ActionRow
                icon={<Activity size={18} />}
                label="Log movement"
                hint="Workout, practice, run — self-reported"
                tone="moss"
                onClick={() => setMovementOpen(true)}
              />
              <ActionRow
                icon={<PenTool size={18} />}
                label={todayJournal && todayJournal.id ? 'Edit today\u2019s journal' : 'Write in journal'}
                hint={
                  todayJournal && todayJournal.id
                    ? 'You already wrote today \u2014 edit it'
                    : 'Dictate or type a memory for today'
                }
                tone="royal"
                onClick={openJournal}
              />
              {/* Use the same feature names as the Tasks tabs. */}
              <ActionRow
                icon={<BookOpen size={18} />}
                label="Log a grade"
                hint="Keep a result and what you learned"
                tone="royal"
                onClick={() => setGradeOpen(true)}
              />
              <ActionRow
                icon={<BookOpen size={18} />}
                label="Add homework"
                hint="Self-assign homework"
                tone="royal"
                onClick={() => setHomeworkOpen(true)}
              />
              {hasDueHw && (
                <ActionRow
                  icon={<BookOpen size={18} />}
                  label="Submit homework"
                  hint={firstDueHw?.title || 'Homework that is due'}
                  tone="teal"
                  onClick={() => {
                    if (firstDueHw) setSubmitAssignment(firstDueHw);
                    else { onClose(); navigate('/quests?tab=study'); }
                  }}
                />
              )}
              <ActionRow
                  icon={<Sparkles size={18} />}
                  label="View challenges"
                  hint="Matching goals progress automatically"
                  tone="moss"
                  onClick={() => { onClose(); navigate('/trials'); }}
                />
              <ActionRow
                icon={<Box size={18} />}
                label="Ask for a print"
                hint="3D print request — parent approves it"
                tone="teal"
                onClick={() => { onClose(); navigate('/quests?tab=forge&new=1'); }}
              />
              <ActionRow
                icon={<Sparkles size={18} />}
                label="Suggest a chore"
                hint="Suggest a chore — parent sets the reward"
                tone="gold"
                onClick={() => { onClose(); navigate('/quests?tab=duties&propose=1'); }}
              />
              <ActionRow
                icon={<Feather size={18} />}
                label="Suggest a habit"
                hint="Suggest a habit — parent sets the XP"
                tone="royal"
                onClick={() => { onClose(); navigate('/quests?tab=rituals&propose=1'); }}
              />
              <ActionRow
                icon={<Target size={18} />}
                label={hasGoals ? 'View savings goals' : 'Set a savings goal'}
                tone="moss"
                onClick={() => { onClose(); navigate('/treasury?tab=hoards'); }}
              />
            </>
          )}

          {isParent && (
            <>
              <ActionRow
                icon={<BookOpen size={18} />}
                label="Assign homework"
                hint="Homework for a kid"
                tone="royal"
                onClick={() => { onClose(); navigate('/quests?tab=study&new=1'); }}
              />
              <ActionRow
                icon={<CoinIcon size={18} />}
                label="Adjust coins"
                tone="gold"
                onClick={() => { onClose(); navigate('/treasury?tab=bazaar&adjust=1'); }}
              />
              <ActionRow
                icon={<UserCog size={18} />}
                label="Adjust payment"
                tone="ember"
                onClick={() => { onClose(); navigate('/treasury?tab=coffers&adjust=1'); }}
              />
            </>
          )}
        </div>
      )}

      {pane === 'clock' && (
        <ClockPane
          status={status}
          isClocked={isClocked}
          elapsedSecs={elapsedSecs}
          projects={projects}
          onBack={() => setPane('menu')}
          onClockReload={onClockReload}
          notes={clockNotes}
          setNotes={setClockNotes}
          busy={clockBusy}
          setBusy={setClockBusy}
        />
      )}
    </BottomSheet>
    </>
  );
}

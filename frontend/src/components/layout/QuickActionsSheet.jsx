import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Square, BookOpen, Target, CircleDollarSign, UserCog, PenTool, Palette } from 'lucide-react';
import BottomSheet from '../BottomSheet';
import { DragonIcon } from '../icons/JournalIcons';
import {
  clockIn, clockOut, getProjects,
  createHomework, getHomeworkDashboard,
  getSavingsGoals, getInventory,
  getTodayJournal,
} from '../../api';
import { useApi, useAuth } from '../../hooks/useApi';
import { normalizeList } from '../../utils/api';
import Button from '../Button';
import { TextField, SelectField, TextAreaField } from '../form';
import JournalEntryFormModal from '../../pages/yearbook/JournalEntryFormModal';
import CreationLogModal from '../CreationLogModal';

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
      className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl border border-ink-page-shadow bg-ink-page hover:bg-ink-page-rune-glow transition-colors disabled:opacity-50 text-left"
    >
      <span className={`${toneText} shrink-0`}>{icon}</span>
      <span className="flex-1 min-w-0">
        <span className="block font-body text-sm font-semibold text-ink-primary">
          {label}
        </span>
        {hint && (
          <span className="block font-script text-xs text-ink-whisper truncate">{hint}</span>
        )}
      </span>
    </button>
  );
}

function ClockPane({ status, isClocked, elapsedSecs, onBack, onClockReload }) {
  const { data: projectsData } = useApi(getProjects);
  const projects = normalizeList(projectsData);
  const [selectedProject, setSelectedProject] = useState('');
  const [notes, setNotes] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleIn = async () => {
    if (!selectedProject) { setError('Select a venture first'); return; }
    setBusy(true); setError('');
    try {
      await clockIn(parseInt(selectedProject, 10));
      await onClockReload();
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
      onBack();
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-3">
      <button type="button" onClick={onBack} className="font-script text-sm text-sheikah-teal-deep hover:underline">
        ← Back
      </button>
      {isClocked ? (
        <>
          <div className="font-script text-ink-whisper text-xs uppercase tracking-wider">Time still inking</div>
          <div className="font-display text-lg truncate">{status?.project_title}</div>
          <div className="font-rune text-3xl font-bold text-ember-deep tabular-nums text-center">
            {formatClock(elapsedSecs)}
          </div>
          <TextAreaField
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Scribble what you did…"
            rows={3}
          />
          {error && <div className="text-ember-deep text-sm font-script">{error}</div>}
          <Button
            variant="danger"
            onClick={handleOut}
            disabled={busy}
            className="w-full flex items-center justify-center gap-2"
          >
            <Square size={18} /> Clock Out
          </Button>
        </>
      ) : (
        <>
          <SelectField
            id="qa-clock-project"
            label="Which venture?"
            value={selectedProject}
            onChange={(e) => setSelectedProject(e.target.value)}
          >
            <option value="">Select a project…</option>
            {projects.filter((p) => ['active', 'in_progress'].includes(p.status)).map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </SelectField>
          {error && <div className="text-ember-deep text-sm font-script">{error}</div>}
          <Button
            onClick={handleIn}
            disabled={busy}
            className="w-full flex items-center justify-center gap-2"
          >
            <Play size={18} /> Clock In
          </Button>
        </>
      )}
    </div>
  );
}

function AddHomeworkPane({ onBack, onDone }) {
  const [title, setTitle] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    if (!title.trim()) { setError('Title is required'); return; }
    setBusy(true); setError('');
    try {
      await createHomework({
        title: title.trim(),
        due_date: dueDate || null,
      });
      onDone && onDone();
      onBack();
    } catch (err) {
      setError(err?.message || 'Could not save assignment.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <button type="button" onClick={onBack} className="font-script text-sm text-sheikah-teal-deep hover:underline">
        ← Back
      </button>
      <TextField
        id="qa-hw-title"
        label="Title"
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="e.g. Math worksheet"
        autoFocus
      />
      <TextField
        id="qa-hw-due"
        label="Due date"
        type="date"
        value={dueDate}
        onChange={(e) => setDueDate(e.target.value)}
      />
      {error && <div className="text-ember-deep text-sm font-script">{error}</div>}
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onBack} className="flex-1">Cancel</Button>
        <Button type="submit" disabled={busy} className="flex-1">
          {busy ? 'Saving…' : 'Add homework'}
        </Button>
      </div>
    </form>
  );
}

/**
 * QuickActionsSheet — contextual action launcher shown by QuickActionsFab.
 * Role-aware and hide rules:
 *   - Child: Clock, Add homework, Submit homework (only if due),
 *            Start quest (only if scroll in inventory),
 *            Request reward, Contribute to savings goal (only if goals exist).
 *   - Parent: Clock (rare), Create chore, Create homework, Adjust coins,
 *            Adjust payment.
 */
export default function QuickActionsSheet({
  status, isClocked, elapsedSecs, onClose, onClockReload,
}) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isParent = user?.role === 'parent';
  const [pane, setPane] = useState('menu'); // 'menu' | 'clock' | 'add-homework'
  const [journalOpen, setJournalOpen] = useState(false);
  const [creationOpen, setCreationOpen] = useState(false);
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
  const { data: inventoryData } = useApi(isParent ? () => Promise.resolve([]) : getInventory);

  const hasDueHw = !isParent && (
    normalizeList(hwDashboard?.today).length > 0 ||
    normalizeList(hwDashboard?.overdue).length > 0
  );
  const firstDueHw = hasDueHw
    ? normalizeList(hwDashboard.overdue)[0] || normalizeList(hwDashboard.today)[0]
    : null;
  const hasGoals = !isParent && normalizeList(goalsData).some((g) => !g.is_completed);
  const hasScroll = !isParent && normalizeList(inventoryData).some(
    (row) => row.item?.item_type === 'quest_scroll' && (row.quantity ?? 0) > 0,
  );

  return (
    <>
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
    <BottomSheet title={pane === 'menu' ? 'Quick actions' : pane === 'clock' ? 'Clock' : 'Add homework'} onClose={onClose}>
      {pane === 'menu' && (
        <div className="space-y-2">
          <ActionRow
            icon={isClocked ? <Square size={18} /> : <Play size={18} />}
            label={isClocked ? 'Stop clock' : 'Clock in'}
            hint={isClocked ? status?.project_title : 'Open an entry'}
            tone={isClocked ? 'ember' : 'teal'}
            onClick={() => setPane('clock')}
          />

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
              <ActionRow
                icon={<BookOpen size={18} />}
                label="Add homework"
                hint="Self-assign an assignment"
                tone="royal"
                onClick={() => setPane('add-homework')}
              />
              {hasDueHw && (
                <ActionRow
                  icon={<BookOpen size={18} />}
                  label="Submit homework"
                  hint={firstDueHw?.title || 'Turn in due work'}
                  tone="teal"
                  onClick={() => {
                    onClose();
                    navigate(firstDueHw ? `/quests?tab=study&submit=${firstDueHw.id}` : '/quests?tab=study');
                  }}
                />
              )}
              {hasScroll && (
                <ActionRow
                  icon={<DragonIcon size={18} />}
                  label="Start a quest"
                  hint="Spend a scroll"
                  tone="moss"
                  onClick={() => { onClose(); navigate('/quests?tab=trials'); }}
                />
              )}
              <ActionRow
                icon={<Target size={18} />}
                label={hasGoals ? 'View hoards' : 'Set a savings goal'}
                tone="moss"
                onClick={() => { onClose(); navigate('/treasury?tab=hoards'); }}
              />
            </>
          )}

          {isParent && (
            <>
              <ActionRow
                icon={<BookOpen size={18} />}
                label="Create homework for a kid"
                tone="royal"
                onClick={() => { onClose(); navigate('/quests?tab=study&new=1'); }}
              />
              <ActionRow
                icon={<CircleDollarSign size={18} />}
                label="Adjust coins"
                tone="gold"
                onClick={() => { onClose(); navigate('/manage?tab=coins'); }}
              />
              <ActionRow
                icon={<UserCog size={18} />}
                label="Adjust payment"
                tone="ember"
                onClick={() => { onClose(); navigate('/manage?tab=payments'); }}
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
          onBack={() => setPane('menu')}
          onClockReload={onClockReload}
        />
      )}

      {pane === 'add-homework' && (
        <AddHomeworkPane
          onBack={() => setPane('menu')}
          onDone={() => { /* parent may wish to reload */ }}
        />
      )}
    </BottomSheet>
    </>
  );
}

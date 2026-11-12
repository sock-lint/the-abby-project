import { useMemo, useState } from 'react';
import useSearchParamState from '../hooks/useSearchParamState';
import { useSearchParams } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { Plus, ThumbsUp, ThumbsDown, Pencil, Trash2 } from 'lucide-react';
import {
  getHabitHistory, getHabits, createHabit, updateHabit, deleteHabit, logHabitTap,
  listMyHabitProposals, approveHabitProposal,
  getAllSkills,
} from '../api';
import { useSpace } from '../hooks/useSpace';
import { useApi } from '../hooks/useApi';
import useMountedRef from '../hooks/useMountedRef';
import { useFormState } from '../hooks/useFormState';
import useChildContext from '../hooks/useChildContext';
import ChildContext from '../components/family/ChildContext';
import { getFamilyHabits, getFamilyHabitProposals } from '../api';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import EmptyState from '../components/EmptyState';
import FilteredEmptyState from '../components/FilteredEmptyState';
import CatalogSearch from '../components/CatalogSearch';
import ConfirmDialog from '../components/ConfirmDialog';
import BottomSheet from '../components/BottomSheet';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import SkillTagEditor from '../components/SkillTagEditor';
import ChapterRubric from '../components/atlas/ChapterRubric';
import { ScrollIcon } from '../components/icons/JournalIcons';
import Button from '../components/Button';
import IconButton from '../components/IconButton';
import ModalActions from '../components/ModalActions';
import { TextField, SelectField } from '../components/form';
import { normalizeList } from '../utils/api';
import { hapticTap } from '../utils/haptics';
import QuestFolio from './quests/QuestFolio';
import IconPicker from '../components/form/IconPicker';
import { HABIT_ICONS } from '../components/form/iconPickerOptions';

// Strength color — journal-safe sepia gradient from ember (low) through
// moss (positive) to royal (mastered).
function getStrengthColor(strength) {
  if (strength < -5) return 'bg-ember-deep text-ink-page-rune-glow';
  if (strength < 0)  return 'bg-ember text-ink-page-rune-glow';
  if (strength === 0) return 'bg-gold-leaf text-ink-primary';
  if (strength <= 5) return 'bg-moss/80 text-ink-page-rune-glow';
  if (strength <= 10) return 'bg-moss text-ink-page-rune-glow';
  return 'bg-royal text-ink-page-rune-glow';
}

// 14-day tap history mini-bars. Moss bars are net-positive days, ember
// bars net-negative; quiet days render a faint 2px stub so the timeline
// keeps its rhythm. Hidden entirely until the habit has at least one tap
// in the window — a fresh ritual shouldn't open with an empty ruler.
function HabitHistoryBars({ series }) {
  if (!series || !series.some((p) => p.net !== 0)) return null;
  const max = Math.max(...series.map((p) => Math.abs(p.net)), 1);
  return (
    <div
      role="img"
      aria-label={`Tap history, last ${series.length} days`}
      className="flex items-end gap-[3px] h-6 mt-3"
    >
      {series.map((p) => {
        const heightPx = p.net === 0 ? 2 : Math.max(4, Math.round((Math.abs(p.net) / max) * 24));
        const tone = p.net > 0 ? 'bg-moss' : p.net < 0 ? 'bg-ember' : 'bg-ink-page-shadow';
        return (
          <span
            key={p.date}
            title={`${p.date}: ${p.net > 0 ? '+' : ''}${p.net}`}
            style={{ height: `${heightPx}px` }}
            className={`flex-1 rounded-sm ${tone}`}
          />
        );
      })}
    </div>
  );
}

function HabitFormModal({ habit, children, skills, isParent, canManage, initialChildId, mode, onClose, onSaved }) {
  const mounted = useMountedRef();
  const resolvedMode = mode || (habit ? 'edit' : 'create');
  const isApprove = resolvedMode === 'approve';
  const isEdit = resolvedMode === 'edit';
  const canSetRewards = canManage;
  const [advanced, setAdvanced] = useState(resolvedMode !== 'create');

  const { form, set, saving, setSaving, error, setError, dirty } = useFormState({
    name: habit?.name || '',
    icon: habit?.icon || '',
    habit_type: habit?.habit_type || 'positive',
    user: habit?.user ?? initialChildId ?? '',
    xp_reward: habit?.xp_reward ?? 5,
    max_taps_per_day: habit?.max_taps_per_day ?? 1,
    skill_tags: (habit?.skill_tags || []).map((t) => ({
      skill_id: t.skill,
      xp_weight: t.xp_weight,
    })),
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isParent && !children?.some((child) => String(child.id) === String(form.user))) {
      setError('Choose a child from your family before creating a habit.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const base = {
        name: form.name,
        icon: form.icon,
        habit_type: form.habit_type,
        max_taps_per_day: Math.max(1, parseInt(form.max_taps_per_day) || 1),
      };
      const parentExtras = canSetRewards ? {
        user: form.user ? parseInt(form.user) : null,
        xp_reward: parseInt(form.xp_reward) || 0,
        skill_tags: form.skill_tags,
      } : {};
      const payload = { ...base, ...parentExtras };

      if (isApprove) {
        await approveHabitProposal(habit.id, payload);
      } else if (isEdit) {
        await updateHabit(habit.id, payload);
      } else {
        await createHabit(payload);
      }
      if (!mounted.current) return;
      onSaved(isParent ? form.user : undefined);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const title = isApprove
    ? 'Approve habit proposal'
    : isEdit
      ? 'Edit habit'
      : canManage ? 'New habit' : 'Propose a habit';
  const submitLabel = isApprove
    ? 'Approve & publish'
    : isEdit ? 'Update habit'
    : canManage ? 'Create habit' : 'Send to parent';

  return (
    <BottomSheet title={title} onClose={onClose} disabled={saving} dirty={dirty}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        {isApprove && habit?.created_by_name && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-body text-ink-primary">
            Proposed by <span className="font-body font-medium">{habit.created_by_name}</span>
            {' — set XP + skill tags below and publish to their habit list.'}
          </div>
        )}
        {!canSetRewards && !isApprove && (
          <div className="rounded-md border border-gold-leaf/40 bg-gold-leaf/10 px-3 py-2 font-script text-body text-ink-primary">
            Your parent will set the rewards when they approve this.
          </div>
        )}
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        {isParent && <SelectField
          label="Child"
          value={form.user}
          onChange={onField('user')}
          required
          disabled={isEdit && Boolean(habit?.starter_key)}
          helpText={isEdit && habit?.starter_key ? 'This starter habit stays with this child.' : undefined}
        >
          <option value="">Choose a child…</option>
          {children?.map((child) => <option key={child.id} value={child.id}>{child.display_name || child.username}</option>)}
        </SelectField>}
        <TextField label="Times per day" type="number" min="1" max="50" value={form.max_taps_per_day} onChange={onField('max_taps_per_day')} helpText="Positive logs allowed each day." />
        {canManage && <Button variant="ghost" aria-expanded={advanced} onClick={() => setAdvanced((value) => !value)}>Advanced options</Button>}
        {(!canManage || advanced) && <div className="space-y-3">
          <IconPicker value={form.icon} onChange={(icon) => set({ icon })} disabled={saving} options={HABIT_ICONS} />
          <SelectField label="Type" value={form.habit_type} onChange={onField('habit_type')}>
            <option value="positive">Build a habit (+)</option><option value="negative">Reduce a habit (−)</option><option value="both">Both</option>
          </SelectField>
          {canSetRewards && <>
            <TextField label="XP pool" type="number" min="0" value={form.xp_reward} onChange={onField('xp_reward')} />
            <SkillTagEditor skills={skills} value={form.skill_tags} onChange={(tags) => set({ skill_tags: tags })} />
          </>}
        </div>}
        {/* Cancel + submit pair, matching the sibling Duties sheet
            (ChoreFormModal) and every other domain form modal. */}
        <ModalActions
          onClose={onClose}
          submitLabel={submitLabel}
          saving={saving}
        />
      </form>
    </BottomSheet>
  );
}

export default function Habits() {
  const context = useChildContext();
  if (!context.user?.id || context.loading) return <Loader />;
  if (context.error) return <ErrorAlert message={context.error} onRetry={context.reload} />;
  return <HabitsWorkspace key={`${context.scope}:${context.targetUserId}`} context={context} />;
}

function HabitsWorkspace({ context }) {
  const mounted = useMountedRef();
  const [searchParams, setSearchParams] = useSearchParams();
  const { isParent, children = [], targetUserId, selectedChild, selectChild } = context;
  const { isParentAccount } = useSpace();
  const canManage = isParentAccount;
  const { data: rawHabits, loading, refreshing, error: habitsError, reload } = useApi(isParent ? getFamilyHabits : getHabits, [isParent]);
  const { data: tapHistory, error: historyError, reload: reloadHistory } = useApi(getHabitHistory);
  const { data: rawProposals, error: proposalsError, reload: reloadProposals } = useApi(
    isParent ? getFamilyHabitProposals : listMyHabitProposals,
    [isParent],
  );
  const { data: rawSkills, error: skillsError, reload: reloadSkills } = useApi(
    (signal) => canManage ? getAllSkills({ includeRetired: true, signal }) : Promise.resolve([]),
    [canManage],
  );
  const [proposeParam, setProposeParam] = useSearchParamState('propose', '');
  const [error, setError] = useState('');
  // The quick-actions FAB deep-links here with ?propose=1; without this the
  // row just landed on the tab and the kid had to find the button again.
  const [showForm, setShowForm] = useState(proposeParam === '1');
  const [editingHabit, setEditingHabit] = useState(null);
  const [formMode, setFormMode] = useState('create');
  const [confirmDelete, setConfirmDelete] = useState(null);
  const [tapping, setTapping] = useState(null);
  const [togglingActive, setTogglingActive] = useState(null);
  const [search, setSearch] = useState('');
  // Optimistic deltas keyed by habit id — `{ [id]: {strength, taps_today} }`.
  // Applied during render so the strength medallion bumps the moment a
  // tap fires instead of waiting on the server roundtrip + refetch.
  // Cleared on reload so server values are authoritative once the
  // refetch lands; on error we also clear so we don't ghost a phantom.
  const [tapDeltas, setTapDeltas] = useState({});

  const habitsRaw = normalizeList(rawHabits).filter((habit) => canManage
    ? String(habit.user) === String(targetUserId)
    : habit.is_active !== false);
  const habits = habitsRaw.map((h) => {
    const d = tapDeltas[h.id];
    if (!d) return h;
    return {
      ...h,
      strength: (h.strength ?? 0) + (d.strength || 0),
      taps_today: (h.taps_today ?? 0) + (d.taps_today || 0),
    };
  });

  const filteredHabits = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return habits;
    return habits.filter((h) => (h.name || '').toLowerCase().includes(q));
  }, [habits, search]);

  const proposals = normalizeList(rawProposals).filter((proposal) => !isParent || String(proposal.user) === String(targetUserId));
  const skills = normalizeList(rawSkills);

  const refreshAll = () => {
    reload();
    reloadProposals();
  };

  const openCreate = () => {
    setEditingHabit(null);
    setFormMode('create');
    setShowForm(true);
  };
  // Drop ?propose=1 as the sheet closes so a tab switch back here (ChapterHub
  // remounts tab bodies) doesn't re-open it.
  const closeForm = () => {
    setShowForm(false);
    setEditingHabit(null);
    setProposeParam('');
  };
  const handleSaved = (childId) => {
    if (isParent && String(childId) !== String(targetUserId) && children.some((child) => String(child.id) === String(childId))) {
      setShowForm(false);
      setEditingHabit(null);
      const next = new URLSearchParams(searchParams);
      next.delete('propose');
      next.set('child', String(childId));
      setSearchParams(next, { replace: true });
    } else {
      closeForm();
      refreshAll();
    }
  };
  const openEdit = (habit) => {
    setEditingHabit(habit);
    setFormMode('edit');
    setShowForm(true);
  };
  const openApprove = (habit) => {
    setEditingHabit(habit);
    setFormMode('approve');
    setShowForm(true);
  };

  const handleTap = async (habit, direction) => {
    // Same tap, same buzz as the dashboard's quick habit tap (ChildDashboard).
    hapticTap();
    setTapping(`${habit.id}-${direction}`);
    setError('');
    // Optimistic bump — strength shifts by direction, positive taps also
    // count against today's cap. The medallion + "X/Y today" line both
    // update before the server roundtrip lands so a tap reads as instant.
    setTapDeltas((prev) => {
      const cur = prev[habit.id] || { strength: 0, taps_today: 0 };
      return {
        ...prev,
        [habit.id]: {
          strength: cur.strength + direction,
          taps_today: cur.taps_today + (direction === 1 ? 1 : 0),
        },
      };
    });
    try {
      await logHabitTap(habit.id, direction);
      if (!mounted.current) return;
      // Reconcile with the server — clear our optimistic delta for this
      // habit and refetch the canonical row.
      setTapDeltas((prev) => {
        const { [habit.id]: _drop, ...rest } = prev;
        return rest;
      });
      reload();
      reloadHistory();
    } catch (err) {
      // Roll back on failure so the medallion doesn't ghost a phantom value.
      setTapDeltas((prev) => {
        const { [habit.id]: _drop, ...rest } = prev;
        return rest;
      });
      setError(err.message);
    } finally {
      setTapping(null);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    setError('');
    try {
      await deleteHabit(confirmDelete.id);
      if (!mounted.current) return;
      setConfirmDelete(null);
      refreshAll();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleToggleActive = async (habit) => {
    if (togglingActive !== null) return;
    setTogglingActive(habit.id);
    setError('');
    try {
      await updateHabit(habit.id, { is_active: habit.is_active === false });
      if (!mounted.current) return;
      await reload();
    } catch (err) {
      if (mounted.current) setError(err.message);
    } finally {
      if (mounted.current) setTogglingActive(null);
    }
  };

  if (loading) return <Loader />;

  // Verso math — average strength tells the chapter-level story; the
  // medallions on each ritual row carry the per-habit detail. Render the
  // average as a one-decimal float so it never collides with the raw
  // integer strength values shown on the medallions (which tests assert
  // on via getByText('3')).
  const avgStrength = habits.length > 0
    ? habits.reduce((sum, h) => sum + (h.strength ?? 0), 0) / habits.length
    : 0;
  // Map strength → 0-100%: 0 strength → 0%, +10 → 100%. Negative averages
  // pin to 0% (the gentle-nudge doctrine — drifting back is visible but
  // never punished).
  const versoProgressPct = Math.max(0, Math.min(100, Math.round(avgStrength * 10)));
  const versoStats = [
    { value: rawHabits === null ? '—' : habits.length, label: 'habits' },
    { value: rawHabits === null ? '—' : avgStrength.toFixed(1), label: 'avg strength' },
  ];
  const versoProgressLabel = habits.length > 0
    ? `${habits.length} habit${habits.length === 1 ? '' : 's'} ${isParent ? 'added' : 'in practice'}`
    : rawHabits === null ? 'Habits unavailable' : '0 habits added';

  let rubricIndex = 0;
  const nextRubric = () => rubricIndex++;

  return (
    <div className="space-y-6">
      <QuestFolio
        letter="H"
        title="Habits"
        kicker="Build everyday habits"
        meta={isParent ? 'Review this child’s daily habits and manage their routine.' : 'Log your habits each day. Habit strength moves toward zero on missed days.'}
        stats={versoStats}
        progressPct={versoProgressPct}
        progressLabel={versoProgressLabel}
      >
        <ErrorAlert message={error} />
        <ErrorAlert message={habitsError && `${rawHabits === null ? "Couldn't load habits." : "Couldn't update habits. Showing the last loaded list."} ${habitsError}`} onRetry={reload} />
        <ErrorAlert message={proposalsError && `Couldn't load habit proposals. ${proposalsError}`} onRetry={reloadProposals} />
        <ErrorAlert message={historyError && `Couldn't load habit history. ${historyError}`} onRetry={reloadHistory} />
        <ErrorAlert message={skillsError && `Couldn't load skills for habits. ${skillsError}`} onRetry={reloadSkills} />
        {refreshing && <p role="status" className="text-caption text-ink-secondary">Updating habits…</p>}

        {isParent && <ChildContext children={children} selectedChildId={targetUserId} onSelect={selectChild} />}
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={openCreate}
            className="flex items-center gap-1.5"
          >
            <Plus size={16} /> {canManage ? 'New habit' : 'Propose a habit'}
          </Button>
        </div>

        {proposals.length > 0 && (
          <section>
            <ChapterRubric
              index={nextRubric()}
              name={isParent ? 'Habit proposals awaiting review' : 'Your proposals'}
            />
            <div className="space-y-2">
              {proposals.map((p) => (
                <ParchmentCard key={p.id} className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-body text-body font-medium text-ink-primary flex items-center gap-2">
                      <span className="text-lg">{p.icon || '⚡'}</span>
                      {p.name}
                      <RuneBadge tone="ember" size="sm">pending</RuneBadge>
                    </div>
                    <div className="font-script text-caption text-ink-whisper">
                      {isParent
                        ? `proposed by ${p.created_by_name || 'child'}`
                        : 'waiting for parent to set XP'}
                    </div>
                  </div>
                  <div className="shrink-0 flex gap-1">
                    {isParent ? (
                      <>
                        <Button size="sm" onClick={() => openApprove(p)}>
                          Review &amp; publish
                        </Button>
                        <IconButton
                          variant="danger"
                          onClick={() => setConfirmDelete(p)}
                          aria-label="Decline proposal"
                          className="min-w-[44px] min-h-[44px]"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </>
                    ) : (
                      <RuneBadge tone="ink" size="sm">pending</RuneBadge>
                    )}
                  </div>
                </ParchmentCard>
              ))}
            </div>
          </section>
        )}

        <section>
          <ChapterRubric
            index={nextRubric()}
            name={isParent ? 'Habits' : 'Active habits'}
            icon={<ScrollIcon size={18} className="text-sheikah-teal-deep" />}
          />
          {habits.length > 0 && (
            <div className="mb-3">
              <CatalogSearch
                value={search}
                onChange={setSearch}
                placeholder="Search habits…"
                ariaLabel="Filter habits"
              />
            </div>
          )}
          {rawHabits === null ? null : habits.length === 0 ? (
            <EmptyState icon={<ScrollIcon size={32} />}>
              No habits yet. Add or propose a habit to get started.
            </EmptyState>
          ) : filteredHabits.length === 0 ? (
            <FilteredEmptyState query={search.trim()} onClear={() => setSearch('')} icon={<ScrollIcon size={32} />} />
          ) : (
            <motion.div layout className="grid lg:grid-cols-2 2xl:grid-cols-3 gap-3">
          <AnimatePresence>
            {filteredHabits.map((habit) => (
              <motion.div
                key={habit.id}
                layout
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <ParchmentCard>
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-11 h-11 rounded-full flex items-center justify-center font-rune text-body font-bold shrink-0 shadow-sm ${getStrengthColor(habit.strength ?? 0)}`}
                    >
                      {habit.strength ?? 0}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {habit.icon && <span className="text-lg shrink-0">{habit.icon}</span>}
                        <span className="min-w-0 break-words [overflow-wrap:anywhere] font-display text-base text-ink-primary">
                          {habit.name}
                        </span>
                      </div>
                      {habit.is_active === false && <RuneBadge tone="ink" size="sm" className="mt-1">Paused</RuneBadge>}
                      {isParent && <p className="font-body text-caption text-ink-secondary">For {selectedChild?.display_name || selectedChild?.username}</p>}
                      {habit.starter_key === 'brush_teeth' && habit.max_taps_per_day === 2 && (
                        <p className="font-body text-caption text-ink-secondary mt-0.5">Twice a day · morning and evening</p>
                      )}
                      <div className="font-script text-caption text-ink-whisper mt-0.5">
                        {habit.xp_reward > 0 && (!habit.starter_key || habit.skill_tags?.length > 0) && <span>{habit.xp_reward} XP</span>}
                        {habit.xp_reward > 0 && (!habit.starter_key || habit.skill_tags?.length > 0) && habit.max_taps_per_day > 0 && <span> · </span>}
                        {habit.max_taps_per_day > 0 && (
                          <span>
                            {habit.taps_today ?? 0}/{habit.max_taps_per_day} today
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <HabitHistoryBars series={tapHistory?.histories?.[String(habit.id)]} />

                  <div className="flex items-center justify-between mt-3 pt-3 border-t border-ink-page-shadow/70">
                    <div className="flex gap-2">
                      {!isParent && (habit.habit_type === 'positive' || habit.habit_type === 'both') && (() => {
                        const atCap = (habit.taps_today ?? 0) >= (habit.max_taps_per_day ?? 1);
                        const brushing = habit.starter_key === 'brush_teeth';
                        const label = brushing
                          ? (atCap ? 'Done for today' : 'I brushed my teeth')
                          : (atCap ? 'done' : 'Log progress');
                        return (
                          <Button
                            variant="success"
                            size="sm"
                            onClick={() => handleTap(habit, 1)}
                            disabled={tapping === `${habit.id}-1` || atCap || habit.is_active === false}
                            title={atCap ? `Daily limit reached (${habit.max_taps_per_day}/day)` : undefined}
                            className="flex items-center gap-1"
                          >
                            <ThumbsUp size={14} /> {label}
                          </Button>
                        );
                      })()}
                      {!isParent && (habit.habit_type === 'negative' || habit.habit_type === 'both') && (
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => handleTap(habit, -1)}
                          disabled={tapping === `${habit.id}--1` || habit.is_active === false}
                          className="flex items-center gap-1"
                        >
                          <ThumbsDown size={14} /> Log setback
                        </Button>
                      )}
                    </div>
                    {canManage && (
                      <div className="flex flex-wrap gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleToggleActive(habit)}
                          disabled={togglingActive !== null}
                          aria-busy={togglingActive === habit.id || undefined}
                        >
                          {habit.is_active === false ? 'Resume' : 'Pause'}
                        </Button>
                        <IconButton
                          onClick={() => openEdit(habit)}
                          disabled={togglingActive !== null}
                          aria-label="Edit habit"
                        >
                          <Pencil size={16} />
                        </IconButton>
                        <IconButton
                          onClick={() => setConfirmDelete(habit)}
                          disabled={togglingActive !== null}
                          aria-label="Delete habit"
                          className="hover:text-ember-deep"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </div>
                    )}
                  </div>
                </ParchmentCard>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        )}
        </section>
      </QuestFolio>

      {showForm && (
        <HabitFormModal
          habit={editingHabit}
          initialChildId={canManage ? targetUserId : undefined}
          children={isParent ? children : null}
          skills={skills}
          isParent={isParent}
          canManage={canManage}
          mode={formMode}
          onClose={closeForm}
          onSaved={handleSaved}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          title="Delete habit"
          message={`Are you sure you want to delete "${confirmDelete.name}"?`}
          onConfirm={handleDelete}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  );
}

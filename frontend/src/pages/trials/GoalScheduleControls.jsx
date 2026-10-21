import { useCallback, useId, useState } from 'react';
import { getAllSkills, updateChallengeSchedule } from '../../api';
import { getToken } from '../../api/client';
import { useApi } from '../../hooks/useApi';
import { useRole } from '../../hooks/useRole';
import useMountedRef from '../../hooks/useMountedRef';
import { fieldErrors, normalizeList } from '../../utils/api';
import { formErrorClass } from '../../constants/styles';
import Button from '../../components/Button';
import BottomSheet from '../../components/BottomSheet';
import ModalActions from '../../components/ModalActions';
import ErrorAlert from '../../components/ErrorAlert';
import SkillTagEditor from '../../components/SkillTagEditor';
import { TextField, TextAreaField } from '../../components/form';
import { goalDate, goalNumber, goalUnit } from './goalDisplay';

function initialSettings(schedule) {
  const next = schedule.next_week;
  return {
    name: next.name || '', description: next.description || '', target: String(next.target),
    coin_reward: String(next.coin_reward), xp_reward: String(next.xp_reward),
    skill_tags: next.skill_tags || [],
  };
}

async function refreshSchedule(onReload, goalId, revision) {
  const response = await onReload?.();
  const schedule = response?.results?.find((row) => row.goal_definition_id === goalId && row.schedule)?.schedule;
  if (!schedule?.next_week || !Number.isInteger(schedule.revision) || schedule.revision <= revision) {
    throw new Error('Could not refresh the saved future settings. Try loading them again.');
  }
  return schedule;
}

export default function GoalScheduleControls({ goal, onChanged, onReload }) {
  const { isParent, user } = useRole();
  const token = getToken();
  if (!isParent || goal.origin !== 'parent' || !goal.schedule?.next_week || !goal.goal_definition_id) return null;
  return <ScheduleControls key={`${user.id}:${user.family?.id ?? ''}:${token}:${goal.goal_definition_id}`} goal={goal} token={token} onChanged={onChanged} onReload={onReload} />;
}

function ScheduleControls({ goal, token, onChanged, onReload }) {
  const mounted = useMountedRef();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [conflictRevision, setConflictRevision] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [confirmedSchedule, setConfirmedSchedule] = useState(null);
  const schedule = confirmedSchedule?.revision > goal.schedule.revision ? confirmedSchedule : goal.schedule;
  const next = schedule.next_week;
  const current = () => mounted.current && getToken() === token;
  const reloadSettings = async () => {
    if (refreshing || !current()) return;
    setRefreshing(true);
    try {
      const fresh = await refreshSchedule(onReload, goal.goal_definition_id, conflictRevision ?? schedule.revision);
      if (!current()) return;
      setConfirmedSchedule(fresh);
      setConflict(false);
      setConflictRevision(null);
      setError('Saved future settings have been refreshed. Review them before trying again.');
    } catch {
      if (current()) setError('Could not refresh the saved future settings. Load them again before making another change.');
    } finally { if (current()) setRefreshing(false); }
  };
  const setPaused = async () => {
    if (saving || refreshing || conflict || !current()) return;
    setSaving(true); setError('');
    try {
      const response = await updateChallengeSchedule(goal.goal_definition_id, { expected_revision: schedule.revision, paused: !next.paused }, { token });
      if (current()) onChanged?.(response);
    } catch (failure) {
      if (!current()) return;
      if (failure.status === 409) {
        setConflict(true);
        setConflictRevision(schedule.revision);
        setError('These future settings changed. Loading the saved version before you try again.');
        await reloadSettings();
      } else setError(failure.message);
    } finally { if (current()) setSaving(false); }
  };
  return <section aria-label="Future weekly goal settings" className="space-y-3 rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3">
    <h3 className="font-body font-bold text-body text-ink-primary">Future weeks</h3>
    <p className="font-body text-body text-ink-secondary">{next.paused ? 'Future weeks are paused.' : 'Future weeks are scheduled.'} Changes take effect from {goalDate(next.starts_at, goal.timezone || 'UTC', true)}. This period&apos;s target, progress and completion bonus stay as promised.</p>
    <p className="font-body text-caption text-ink-secondary">{next.name} · {goalNumber(next.target)} {goalUnit(next.unit, next.target)} · {next.coin_reward} coins · {next.xp_reward} XP</p>
    <ErrorAlert message={error} />
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" disabled={saving || refreshing || conflict} onClick={setPaused}>{next.paused ? 'Resume future weeks' : 'Pause future weeks'}</Button>
      <Button variant="secondary" disabled={saving || refreshing || conflict} onClick={() => setEditing(true)}>Change future weeks</Button>
      {conflict && <Button variant="secondary" disabled={saving || refreshing} onClick={reloadSettings}>Retry saved future settings</Button>}
    </div>
    {refreshing && <p role="status">Loading saved future settings…</p>}
    {editing && <NextWeekGoalForm goal={{ ...goal, schedule }} token={token} onClose={() => setEditing(false)} onChanged={onChanged} onReload={onReload} />}
  </section>;
}

function NextWeekGoalForm({ goal, token, onClose, onChanged, onReload }) {
  const mounted = useMountedRef();
  const formId = useId();
  const skillErrorId = useId();
  const [form, setForm] = useState(() => initialSettings(goal.schedule));
  const [revision, setRevision] = useState(goal.schedule.revision);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const [conflict, setConflict] = useState(false);
  const [refreshedSchedule, setRefreshedSchedule] = useState(null);
  const [refreshingSettings, setRefreshingSettings] = useState(false);
  const [refreshError, setRefreshError] = useState('');
  const fetchSkills = useCallback((signal) => getAllSkills({ includeRetired: true, token, signal }), [token]);
  const { data, loading, refreshing, error: skillsError, reload: reloadSkills } = useApi(fetchSkills, [token]);
  const skills = normalizeList(data);
  const wantsXp = Number(form.xp_reward) > 0;
  const skillsPending = loading || refreshing;
  const next = goal.schedule.next_week;
  const current = () => mounted.current && getToken() === token;
  const patch = (values) => { setForm((previous) => ({ ...previous, ...values })); setErrors({}); };
  const set = (field) => (event) => patch({ [field]: event.target.value });
  const reloadSettings = async () => {
    if (refreshingSettings || !current()) return;
    setRefreshingSettings(true); setRefreshedSchedule(null); setRefreshError('');
    try {
      const fresh = await refreshSchedule(onReload, goal.goal_definition_id, revision);
      if (current()) setRefreshedSchedule(fresh);
    } catch {
      if (current()) setRefreshError('Could not refresh the saved future settings. Your draft is still here. Try loading again.');
    } finally { if (current()) setRefreshingSettings(false); }
  };
  const submit = async (event) => {
    event.preventDefault();
    if (saving || conflict || !current() || (wantsXp && (skillsPending || skillsError))) return;
    if (wantsXp && !form.skill_tags.length) { setErrors({ skill_tags: 'Choose a skill to receive the XP bonus.' }); return; }
    setSaving(true); setError(''); setErrors({});
    try {
      const response = await updateChallengeSchedule(goal.goal_definition_id, {
        expected_revision: revision,
        next_week: { ...form, name: form.name.trim(), coin_reward: Number(form.coin_reward), xp_reward: Number(form.xp_reward) },
      }, { token });
      if (!current()) return;
      onChanged?.(response); onClose();
    } catch (failure) {
      if (!current()) return;
      const nested = failure.response?.next_week;
      const fields = nested && typeof nested === 'object' && !Array.isArray(nested) ? fieldErrors({ response: nested }) : fieldErrors(failure);
      setErrors(fields);
      if (failure.status === 409) {
        setConflict(true);
        setError('These future settings changed. Your draft has been kept. Load the saved future settings and review before saving again.');
        await reloadSettings();
      } else setError(Object.keys(fields).length ? 'Check the highlighted fields.' : failure.message);
    } finally { if (current()) setSaving(false); }
  };
  return <BottomSheet title="Change future weeks" onClose={onClose} disabled={saving} dirty footer={(
    <ModalActions formId={formId} fullWidth onClose={onClose} saving={saving} submitLabel="Save future weeks" submitDisabled={conflict || (wantsXp && (skillsPending || Boolean(skillsError)))} />
  )}>
    <form id={formId} onSubmit={submit} className="space-y-4">
      <p className="font-body text-body text-ink-secondary">These settings apply from {goalDate(next.starts_at, goal.timezone || 'UTC', true)}. Current and already accepted periods keep their original promise. The qualifying activity and measure stay the same.</p>
      <fieldset disabled={saving} className="space-y-4 min-w-0">
        <TextField label="Future goal title" value={form.name} onChange={set('name')} required maxLength={100} error={errors.name} />
        <TextAreaField label="Future goal description" value={form.description} onChange={set('description')} error={errors.description} />
        <TextField label={`Future target (${goalUnit(next.unit, 2)})`} type="number" required min={next.metric === 'count' ? '1' : '0.001'} step={next.metric === 'count' ? '1' : '0.001'} value={form.target} onChange={set('target')} error={errors.target} />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <TextField label="Future Coin bonus" type="number" required min="0" max="10000" step="1" value={form.coin_reward} onChange={set('coin_reward')} error={errors.coin_reward} />
          <TextField label="Future XP bonus" type="number" required min="0" max="10000" step="1" value={form.xp_reward} onChange={set('xp_reward')} error={errors.xp_reward} />
        </div>
        {(wantsXp || errors.skill_tags) && <div role="group" aria-label="Skills this rewards" aria-invalid={errors.skill_tags ? true : undefined} aria-describedby={errors.skill_tags ? skillErrorId : undefined} className="space-y-2">
          {skillsPending && <p role="status">Loading skills…</p>}
          {skillsError && <><ErrorAlert message={skillsError} /><Button variant="secondary" onClick={reloadSkills} disabled={skillsPending}>Retry skills</Button></>}
          <fieldset disabled={skillsPending || Boolean(skillsError)} className="min-w-0"><SkillTagEditor skills={skills} value={form.skill_tags} onChange={(skill_tags) => patch({ skill_tags })} emptyMessage="Choose at least one skill to receive the XP bonus." /></fieldset>
          {!skillsPending && !skillsError && !skills.length && <p>No skills are available for XP rewards. You can save with an XP bonus of 0.</p>}
          {errors.skill_tags && <p role="alert" id={skillErrorId} className={formErrorClass}>{errors.skill_tags}</p>}
        </div>}
      </fieldset>
      <ErrorAlert message={error} />
      <ErrorAlert message={refreshError} />
      {refreshingSettings && <p role="status">Loading saved future settings…</p>}
      {conflict && <div className="flex flex-wrap gap-2">
        <Button variant="secondary" disabled={saving || refreshingSettings || !refreshedSchedule} onClick={() => {
          if (!refreshedSchedule || !current()) return;
          setForm(initialSettings(refreshedSchedule)); setRevision(refreshedSchedule.revision);
          setConflict(false); setRefreshedSchedule(null); setErrors({}); setError('');
        }}>Load saved future settings</Button>
        {refreshError && <Button variant="secondary" disabled={saving || refreshingSettings} onClick={reloadSettings}>Retry saved future settings</Button>}
      </div>}
    </form>
  </BottomSheet>;
}

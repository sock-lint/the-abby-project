import { useCallback, useEffect, useState } from 'react';
import { createChallengeGoal, getSkills, listMovementTypes } from '../../api';
import { useApi } from '../../hooks/useApi';
import useMountedRef from '../../hooks/useMountedRef';
import { normalizeList, fieldErrors } from '../../utils/api';
import Button from '../../components/Button';
import BottomSheet from '../../components/BottomSheet';
import ModalActions from '../../components/ModalActions';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, SelectField, CheckboxField } from '../../components/form';
import SkillTagEditor from '../../components/SkillTagEditor';
import { goalUnit } from './goalDisplay';
import { createRequestId } from '../../utils/requestId';

const ACTIVITIES = [
  ['chore_complete', 'Approved chores'], ['homework_complete', 'Approved homework'],
  ['habit_log', 'Positive habit taps'], ['clock_out', 'Project work'],
  ['milestone_complete', 'Project milestones'], ['movement_session', 'Movement'],
];
const INITIAL = {
  user_id: '', name: '', trigger_type: 'chore_complete', movement_type_id: '',
  metric: 'count', target: '2', unit: 'actions', period: 'this_week',
  start_date: '', end_date: '', repeat_weekly: false, coin_reward: '10', xp_reward: '0', skill_tags: [],
};

export default function CreateGoalForm({ children = [], initialChildId, onCreated, requestOpen = false, onRequestConsumed }) {
  const mounted = useMountedRef();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(INITIAL);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const [savedConflict, setSavedConflict] = useState(false);
  const [requestId, setRequestId] = useState(createRequestId);
  useEffect(() => {
    if (!requestOpen || !children.length) return;
    const child = children.find((row) => String(row.id) === String(initialChildId)) || children[0];
    setForm((previous) => ({ ...previous, user_id: String(child.id) }));
    setOpen(true);
    onRequestConsumed?.();
  }, [requestOpen, children, initialChildId, onRequestConsumed]);
  const fetchTypes = useCallback(() => open ? listMovementTypes() : Promise.resolve([]), [open]);
  const fetchSkills = useCallback(() => open ? getSkills() : Promise.resolve([]), [open]);
  const { data: typesData, loading: typesLoading, error: typesError, reload: reloadTypes } = useApi(fetchTypes, [open]);
  const { data: skillsData } = useApi(fetchSkills, [open]);
  const types = normalizeList(typesData);
  const skills = normalizeList(skillsData);
  const movement = form.trigger_type === 'movement_session';
  const timed = movement || form.trigger_type === 'clock_out';
  const type = types.find((row) => String(row.id) === form.movement_type_id);
  const activityLabel = movement ? type?.name || 'Movement' : ACTIVITIES.find(([id]) => id === form.trigger_type)?.[1];
  const periodLabel = form.period === 'this_week' ? 'this week' : form.period === 'from_today' ? 'over the next 7 days' : `${form.start_date || 'start date'} through ${form.end_date || 'end date'}`;
  const generatedName = `${activityLabel} · ${form.target} ${goalUnit(form.unit, form.target)} ${periodLabel}`;
  const patch = (values) => {
    setForm((previous) => ({ ...previous, ...values }));
  };
  const set = (field) => (event) => patch({ [field]: event.target.value });

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setErrors({});
    try {
      const payload = {
        request_id: requestId,
        user_id: Number(form.user_id), name: form.name.trim() || generatedName,
        trigger_type: form.trigger_type, metric: form.metric, target: form.target,
        unit: form.unit, period: form.period, repeat_weekly: form.repeat_weekly,
        coin_reward: Number(form.coin_reward), xp_reward: Number(form.xp_reward), skill_tags: form.skill_tags,
      };
      if (movement) payload.movement_type_id = Number(form.movement_type_id);
      if (form.period === 'custom') {
        payload.start_date = form.start_date;
        payload.end_date = form.end_date;
      }
      const created = await createChallengeGoal(payload);
      if (!mounted.current) return;
      setOpen(false);
      setForm(INITIAL);
      setRequestId(createRequestId());
      setSavedConflict(false);
      onCreated?.(created, form.user_id);
    } catch (err) {
      if (!mounted.current) return;
      const fields = fieldErrors(err);
      setErrors(fields);
      if (err.status === 409) {
        setSavedConflict(true);
        setError('This challenge was already saved with different details. Your challenges have been refreshed so you can review it.');
        onCreated?.(null);
      } else {
        setError(Object.keys(fields).length ? 'Check the highlighted fields.' : err?.response?.error || err.message || 'Could not create the challenge.');
      }
    } finally {
      setSaving(false);
    }
  };

  if (!children.length) return null;
  return (
    <>
      <Button onClick={() => {
        const child = children.find((row) => String(row.id) === String(initialChildId)) || children[0];
        patch({ user_id: form.user_id || String(child.id) });
        setOpen(true);
      }}>Create challenge</Button>
      {open && <BottomSheet title="Create a challenge" onClose={() => setOpen(false)} disabled={saving} dirty footer={(
        <ModalActions formId="create-challenge-goal" fullWidth onClose={() => setOpen(false)} submitLabel="Create challenge" savingLabel="Creating…" saving={saving} submitDisabled={!form.user_id || (movement && !form.movement_type_id)} />
      )}>
        <form id="create-challenge-goal" onSubmit={submit} className="space-y-4">
          <fieldset disabled={saving} className="space-y-4 min-w-0">
          <p className="font-body text-body text-ink-secondary">Choose measurable work for a child. Progress and the completion bonus are automatic.</p>
          <SelectField label="Child" value={form.user_id} onChange={set('user_id')} error={errors.user_id} required>
            {children.map((child) => <option key={child.id} value={child.id}>{child.display_label || child.display_name || child.username}</option>)}
          </SelectField>
          <SelectField label="Activity" value={form.trigger_type} onChange={(event) => patch({ trigger_type: event.target.value, metric: 'count', unit: 'actions' })} error={errors.trigger_type}>
            {ACTIVITIES.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </SelectField>
          {movement && <>
            <SelectField label="Movement activity" value={form.movement_type_id} onChange={set('movement_type_id')} disabled={typesLoading} error={errors.movement_type_id} required>
              <option value="">Choose an activity…</option>
              {types.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}
            </SelectField>
            {typesError && <><ErrorAlert message={typesError} /><Button variant="secondary" onClick={reloadTypes}>Retry activities</Button></>}
          </>}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <SelectField label="Measure" value={form.metric} onChange={(event) => patch({ metric: event.target.value, unit: event.target.value === 'distance' ? 'mi' : event.target.value === 'minutes' ? 'minutes' : 'actions' })} error={errors.metric}>
              <option value="count">Number of activities</option>
              {timed && <option value="minutes">Total minutes</option>}
              {movement && <option value="distance">Total distance</option>}
            </SelectField>
            <TextField label="Target" type="number" min={form.metric === 'distance' ? '0.001' : '1'} step={form.metric === 'distance' ? '0.001' : '1'} value={form.target} onChange={set('target')} error={errors.target} required />
          </div>
          {form.metric === 'distance' && <SelectField label="Distance unit" value={form.unit} onChange={set('unit')} error={errors.unit}><option value="mi">Miles</option><option value="km">Kilometers</option></SelectField>}
          <SelectField label="Timeframe" value={form.period} onChange={(event) => patch({ period: event.target.value, repeat_weekly: event.target.value === 'this_week' && form.repeat_weekly })} error={errors.period}>
            <option value="this_week">This week</option><option value="from_today">Next 7 days</option><option value="custom">Choose dates</option>
          </SelectField>
          {form.period === 'custom' && <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Start date" type="date" value={form.start_date} onChange={set('start_date')} error={errors.start_date} required />
            <TextField label="End date" type="date" min={form.start_date} value={form.end_date} onChange={set('end_date')} error={errors.end_date} required />
          </div>}
          {form.period === 'this_week' && <CheckboxField label="Repeat each week" checked={form.repeat_weekly} onChange={(event) => patch({ repeat_weekly: event.target.checked })} />}
          <p className="font-body text-caption text-ink-secondary">{form.period === 'this_week' ? 'Already recorded activity from this week counts toward this goal.' : 'Activity recorded within the chosen dates counts toward this goal.'} Dates use your family&apos;s timezone.</p>
          <TextField label="Title (optional)" value={form.name} onChange={set('name')} placeholder={generatedName} maxLength={100} error={errors.name} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Coin bonus" type="number" min="0" max="10000" step="1" value={form.coin_reward} onChange={set('coin_reward')} error={errors.coin_reward} required />
            <TextField label="XP bonus" type="number" min="0" max="10000" step="1" value={form.xp_reward} onChange={set('xp_reward')} error={errors.xp_reward} required />
          </div>
          {Number(form.xp_reward) > 0 && <SkillTagEditor skills={skills} value={form.skill_tags} onChange={(skill_tags) => patch({ skill_tags })} />}
          <section aria-label="Challenge preview" className="rounded-xl bg-ink-page-aged border border-ink-page-shadow p-3 space-y-1">
            <h3 className="font-body font-bold text-body text-ink-primary">Preview</h3>
            <p className="font-body text-body text-ink-primary">{form.name.trim() || generatedName}</p>
            <p className="font-body text-caption text-ink-secondary">{form.repeat_weekly ? 'A fresh target and bonus each week.' : 'One completion bonus.'} +{form.coin_reward} coins · +{form.xp_reward} XP</p>
          </section>
          <ErrorAlert message={error} />
          {savedConflict && <Button variant="secondary" onClick={() => {
            setForm({ ...INITIAL, user_id: form.user_id });
            setRequestId(createRequestId());
            setErrors({});
            setError('');
            setSavedConflict(false);
          }}>New challenge</Button>}
          </fieldset>
        </form>
      </BottomSheet>}
    </>
  );
}

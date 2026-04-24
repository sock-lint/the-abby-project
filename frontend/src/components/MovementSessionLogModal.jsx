import { useEffect, useMemo, useState } from 'react';
import BottomSheet from './BottomSheet';
import Button from './Button';
import ErrorAlert from './ErrorAlert';
import { TextField, SelectField, TextAreaField } from './form';
import { useApi } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import {
  createMovementType,
  getSkills,
  listMovementTypes,
  logMovementSession,
} from '../api';

const INTENSITY_OPTIONS = [
  { value: 'low', label: 'Low — easy pace' },
  { value: 'medium', label: 'Medium — solid effort' },
  { value: 'high', label: 'High — pushed hard' },
];

const NEW_TYPE_SENTINEL = '__new__';

function groupSkillsBySubject(skills) {
  const groups = new Map();
  for (const skill of skills) {
    const key = skill.subject_name || 'Other';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(skill);
  }
  return Array.from(groups.entries());
}

function NewTypeSubForm({ skills, skillsLoading, onCancel, onCreated }) {
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [defaultIntensity, setDefaultIntensity] = useState('medium');
  const [primary, setPrimary] = useState('');
  const [secondary, setSecondary] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const skillsBySubject = useMemo(() => groupSkillsBySubject(skills), [skills]);

  const canSubmit = name.trim().length > 0 && !!primary && !saving;

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError('');
    try {
      const created = await createMovementType({
        name: name.trim(),
        icon: icon.trim(),
        default_intensity: defaultIntensity,
        primary_skill_id: Number(primary),
        secondary_skill_id: secondary ? Number(secondary) : null,
      });
      await onCreated?.(created);
    } catch (err) {
      setError(
        err?.response?.error
          || err?.message
          || 'Could not add this activity.',
      );
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-3">
      <TextField
        id="new-type-name"
        label="Activity name"
        value={name}
        onChange={(e) => setName(e.target.value.slice(0, 64))}
        placeholder="Parkour"
        autoFocus
      />
      <TextField
        id="new-type-icon"
        label="Emoji (optional)"
        value={icon}
        onChange={(e) => setIcon(e.target.value.slice(0, 4))}
        placeholder="🧗"
      />
      <SelectField
        id="new-type-intensity"
        label="Default intensity"
        value={defaultIntensity}
        onChange={(e) => setDefaultIntensity(e.target.value)}
        helpText="The intensity we pre-select next time you pick this activity."
      >
        {INTENSITY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </SelectField>
      <SelectField
        id="new-type-primary"
        label="Primary skill"
        value={primary}
        onChange={(e) => setPrimary(e.target.value)}
        disabled={skillsLoading}
        helpText="Which Physical skill does this work on most?"
      >
        <option value="">Choose a Physical skill…</option>
        {skillsBySubject.map(([subject, list]) => (
          <optgroup key={subject} label={subject}>
            {list.map((skill) => (
              <option key={skill.id} value={skill.id}>
                {skill.icon ? `${skill.icon} ${skill.name}` : skill.name}
              </option>
            ))}
          </optgroup>
        ))}
      </SelectField>
      <SelectField
        id="new-type-secondary"
        label="Secondary skill (optional)"
        value={secondary}
        onChange={(e) => setSecondary(e.target.value)}
        disabled={skillsLoading || !primary}
        helpText="XP splits 70/30 when both are set."
      >
        <option value="">No secondary</option>
        {skillsBySubject.map(([subject, list]) => {
          const filtered = list.filter(
            (skill) => String(skill.id) !== String(primary),
          );
          if (filtered.length === 0) return null;
          return (
            <optgroup key={subject} label={subject}>
              {filtered.map((skill) => (
                <option key={skill.id} value={skill.id}>
                  {skill.icon ? `${skill.icon} ${skill.name}` : skill.name}
                </option>
              ))}
            </optgroup>
          );
        })}
      </SelectField>

      {error && <ErrorAlert message={error} />}

      <div className="flex gap-2 pt-1">
        <Button variant="secondary" type="button" onClick={onCancel} className="flex-1">
          Back
        </Button>
        <Button type="submit" onClick={submit} disabled={!canSubmit} className="flex-1">
          {saving ? 'Saving…' : 'Add activity'}
        </Button>
      </div>
    </form>
  );
}

export default function MovementSessionLogModal({ onClose, onSaved }) {
  const {
    data: typesData,
    loading: typesLoading,
    reload: reloadTypes,
  } = useApi(listMovementTypes);
  const types = normalizeList(typesData);

  const [mode, setMode] = useState('log');
  const [movementTypeId, setMovementTypeId] = useState('');
  const [duration, setDuration] = useState(30);
  const [intensity, setIntensity] = useState('medium');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const { data: skillsData, loading: skillsLoading } = useApi(getSkills);
  const physicalSkills = useMemo(
    () => normalizeList(skillsData).filter((s) => s.category_name === 'Physical'),
    [skillsData],
  );

  const selectedType = useMemo(
    () => types.find((t) => String(t.id) === String(movementTypeId)),
    [types, movementTypeId],
  );

  // When the picked type changes, default the intensity slider to its
  // pre-set default — soccer practice is usually high; yoga is usually low.
  useEffect(() => {
    if (selectedType?.default_intensity) {
      setIntensity(selectedType.default_intensity);
    }
  }, [selectedType]);

  const canSubmit = movementTypeId && duration > 0 && !saving;

  const handlePickerChange = (e) => {
    if (e.target.value === NEW_TYPE_SENTINEL) {
      setMode('new');
      return;
    }
    setMovementTypeId(e.target.value);
  };

  const handleTypeCreated = async (created) => {
    await reloadTypes();
    setMovementTypeId(String(created.id));
    setMode('log');
  };

  const submit = async (e) => {
    if (e?.preventDefault) e.preventDefault();
    if (!canSubmit) return;
    setSaving(true);
    setError('');
    try {
      const saved = await logMovementSession({
        movement_type_id: Number(movementTypeId),
        duration_minutes: Math.min(600, Math.max(1, Number(duration) || 1)),
        intensity,
        notes: notes.trim(),
      });
      onSaved?.(saved);
      onClose?.();
    } catch (err) {
      setError(err?.message || 'Could not log your session.');
    } finally {
      setSaving(false);
    }
  };

  const title = mode === 'new' ? 'Add activity' : 'Log a session';

  return (
    <BottomSheet title={title} onClose={onClose}>
      {mode === 'new' ? (
        <NewTypeSubForm
          skills={physicalSkills}
          skillsLoading={skillsLoading}
          onCancel={() => setMode('log')}
          onCreated={handleTypeCreated}
        />
      ) : (
        <form onSubmit={submit} className="space-y-3">
          <SelectField
            id="movement-type"
            label="What did you do?"
            value={movementTypeId}
            onChange={handlePickerChange}
            disabled={typesLoading}
          >
            <option value="">Choose one…</option>
            {types.map((t) => (
              <option key={t.id} value={t.id}>
                {t.icon ? `${t.icon} ${t.name}` : t.name}
              </option>
            ))}
            <option value={NEW_TYPE_SENTINEL}>+ New activity…</option>
          </SelectField>

          <TextField
            id="movement-duration"
            label="How long? (minutes)"
            type="number"
            min="1"
            max="600"
            step="5"
            value={duration}
            onChange={(e) => setDuration(e.target.value)}
          />

          <SelectField
            id="movement-intensity"
            label="How hard?"
            value={intensity}
            onChange={(e) => setIntensity(e.target.value)}
            helpText="Low = easy. Medium = solid. High = pushed hard."
          >
            {INTENSITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </SelectField>

          <TextAreaField
            id="movement-notes"
            label="Notes (optional)"
            value={notes}
            onChange={(e) => setNotes(e.target.value.slice(0, 200))}
            placeholder="What stood out today?"
            rows={2}
          />

          {error && <ErrorAlert message={error} />}

          <div className="flex gap-2 pt-1">
            <Button variant="secondary" type="button" onClick={onClose} className="flex-1">
              Cancel
            </Button>
            <Button type="submit" onClick={submit} disabled={!canSubmit} className="flex-1">
              {saving ? 'Saving…' : 'Log session'}
            </Button>
          </div>
        </form>
      )}
    </BottomSheet>
  );
}

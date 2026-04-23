import { useEffect, useMemo, useState } from 'react';
import BottomSheet from './BottomSheet';
import Button from './Button';
import ErrorAlert from './ErrorAlert';
import { TextField, SelectField, TextAreaField } from './form';
import { useApi } from '../hooks/useApi';
import { normalizeList } from '../utils/api';
import { listMovementTypes, logMovementSession } from '../api';

const INTENSITY_OPTIONS = [
  { value: 'low', label: 'Low — easy pace' },
  { value: 'medium', label: 'Medium — solid effort' },
  { value: 'high', label: 'High — pushed hard' },
];

export default function MovementSessionLogModal({ onClose, onSaved }) {
  const { data: typesData, loading: typesLoading } = useApi(listMovementTypes);
  const types = normalizeList(typesData);

  const [movementTypeId, setMovementTypeId] = useState('');
  const [duration, setDuration] = useState(30);
  const [intensity, setIntensity] = useState('medium');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

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

  return (
    <BottomSheet title="Log a session" onClose={onClose}>
      <form onSubmit={submit} className="space-y-3">
        <SelectField
          id="movement-type"
          label="What did you do?"
          value={movementTypeId}
          onChange={(e) => setMovementTypeId(e.target.value)}
          disabled={typesLoading}
        >
          <option value="">Choose one…</option>
          {types.map((t) => (
            <option key={t.id} value={t.id}>
              {t.icon ? `${t.icon} ${t.name}` : t.name}
            </option>
          ))}
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
    </BottomSheet>
  );
}

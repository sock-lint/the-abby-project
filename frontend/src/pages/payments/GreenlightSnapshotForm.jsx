import { useRef, useState } from 'react';
import { saveGreenlightSnapshot } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import Button from '../../components/Button';
import ErrorAlert from '../../components/ErrorAlert';
import { TextField, TextAreaField } from '../../components/form';
import { fieldErrors } from '../../utils/api';
import { toISODate } from '../../utils/dates';
import { usePwaUpdateGuard } from '../../pwa/usePwaUpdateGuard';

export default function GreenlightSnapshotForm({ userId, kidName, onClose, onSaved }) {
  const [amount, setAmount] = useState('');
  const [observedAt, setObservedAt] = useState(() => {
    const now = new Date();
    return `${toISODate(now)}T${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  });
  const [memo, setMemo] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [errors, setErrors] = useState({});
  const saved = useRef({ amount, observedAt, memo });
  const dirty = amount !== saved.current.amount || observedAt !== saved.current.observedAt || memo !== saved.current.memo;
  usePwaUpdateGuard(dirty || saving);
  const submit = async (event) => {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setErrors({});
    setError('');
    try {
      await saveGreenlightSnapshot({
        user_id: Number(userId), amount, as_of: new Date(observedAt).toISOString(), memo,
      });
      saved.current = { amount, observedAt, memo };
      onSaved();
    } catch (failure) {
      const fields = fieldErrors(failure);
      setErrors(fields);
      setError(Object.keys(fields).length ? 'Check the balance details below.' : failure.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <BottomSheet title={`Verify ${kidName}’s Greenlight balance`} onClose={onClose} disabled={saving}>
      <p className="text-body text-ink-secondary mb-3">Check the balance in Greenlight and enter it with the time you observed it. This saves a snapshot; it does not change money owed.</p>
      <ErrorAlert message={error} />
      <form onSubmit={submit} className="space-y-3">
        <fieldset disabled={saving} className="space-y-3">
          <TextField label="Verified Greenlight balance" type="number" step="0.01" min="0" required
            value={amount} error={errors.amount} onChange={(event) => setAmount(event.target.value)} />
          <TextField label="Observed at" type="datetime-local" required value={observedAt} error={errors.as_of}
            onChange={(event) => setObservedAt(event.target.value)} />
          <TextAreaField label="Balance memo (optional)" value={memo} maxLength={1000} error={errors.memo}
            onChange={(event) => setMemo(event.target.value)} />
        </fieldset>
        <div className="flex justify-end gap-2 flex-wrap">
          <Button variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save verified balance'}</Button>
        </div>
      </form>
    </BottomSheet>
  );
}

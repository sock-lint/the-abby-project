import { useRef, useState } from 'react';
import { markMaterialReady, markPurchased } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import Button from '../../../components/Button';
import ErrorAlert from '../../../components/ErrorAlert';
import { SelectField, TextField } from '../../../components/form';
import { fieldErrors } from '../../../utils/api';

export default function MaterialReadyModal({ projectId, material, onClose, onSaved }) {
  const [source, setSource] = useState('on_hand');
  const [cost, setCost] = useState(material.actual_cost ?? '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [costError, setCostError] = useState('');
  const pending = useRef(false);
  const purchased = source === 'purchased';

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (pending.current) return;
    pending.current = true;
    setSaving(true);
    setError('');
    setCostError('');
    try {
      if (purchased) await markPurchased(projectId, material.id, Number(cost).toFixed(2));
      else await markMaterialReady(projectId, material.id);
      onSaved();
    } catch (err) {
      const fields = fieldErrors(err);
      if (fields.actual_cost) setCostError(fields.actual_cost);
      else setError(err.message);
    } finally {
      pending.current = false;
      setSaving(false);
    }
  };

  return (
    <BottomSheet
      title="Mark material ready"
      onClose={onClose}
      disabled={saving}
      dirty={source !== 'on_hand' || cost !== (material.actual_cost ?? '')}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="font-body text-body text-ink-primary break-words">{material.name}</p>
        <ErrorAlert message={error} />
        <SelectField
          label="How did you get it?"
          value={source}
          onChange={(event) => { setSource(event.target.value); setCostError(''); setError(''); }}
          disabled={saving}
          autoFocus
        >
          <option value="on_hand">Already have it or borrowing</option>
          <option value="purchased">Purchased</option>
        </SelectField>
        {purchased ? (
          <TextField
            label="Actual cost ($)"
            value={cost}
            onChange={(event) => { setCost(event.target.value); setCostError(''); }}
            type="number"
            min="0"
            max="999999.99"
            step="0.01"
            required
            disabled={saving}
            error={costError}
            helpText="Enter what you paid, including zero for a free item."
          />
        ) : (
          <p className="font-body text-caption text-ink-secondary">
            For supplies you own, borrow, or receive for free.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="secondary" onClick={onClose} disabled={saving} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" loading={saving} disabled={purchased && cost === ''} className="flex-1">
            Mark ready
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

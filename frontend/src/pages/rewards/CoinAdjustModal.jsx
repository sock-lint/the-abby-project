import { adjustCoins, getChildren } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useApi } from '../../hooks/useApi';
import { useFormState } from '../../hooks/useFormState';
import { normalizeList } from '../../utils/api';
import Button from '../../components/Button';
import { TextField, SelectField } from '../../components/form';

export default function CoinAdjustModal({ onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    user_id: '', amount: '', description: '',
  });
  const { data: childrenRes, loading: loadingChildren } = useApi(getChildren);
  const children = normalizeList(childrenRes);

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await adjustCoins(parseInt(form.user_id), parseInt(form.amount), form.description);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Adjust Coins" onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <SelectField
          label="Kid"
          value={form.user_id}
          onChange={onField('user_id')}
          required
          disabled={loadingChildren}
          helpText={loadingChildren ? 'Loading kids…' : (children.length === 0 ? 'No children in this family yet.' : null)}
        >
          <option value="" disabled>Pick a kid</option>
          {children.map((child) => (
            <option key={child.id} value={child.id}>
              {child.display_name || child.username}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Amount (positive to add, negative to deduct)"
          type="number"
          value={form.amount}
          onChange={onField('amount')}
          required
        />
        <TextField
          label="Description"
          value={form.description}
          onChange={onField('description')}
          placeholder="Reason for adjustment"
        />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-whisper hover:text-ink-primary">
            Cancel
          </button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? 'Adjusting...' : 'Adjust'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

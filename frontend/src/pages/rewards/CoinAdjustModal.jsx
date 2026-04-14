import { adjustCoins } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';

export default function CoinAdjustModal({ onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    user_id: '', amount: '', description: '',
  });

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
    <FormModal title="Adjust Coins" onClose={onClose} size="md" scroll={false}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Child User ID</label>
          <input
            className={inputClass}
            type="number"
            value={form.user_id}
            onChange={onField('user_id')}
            required
            placeholder="Enter child user ID"
          />
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">
            Amount (positive to add, negative to deduct)
          </label>
          <input
            className={inputClass}
            type="number"
            value={form.amount}
            onChange={onField('amount')}
            required
          />
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Description</label>
          <input
            className={inputClass}
            value={form.description}
            onChange={onField('description')}
            placeholder="Reason for adjustment"
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-whisper hover:text-ink-primary">
            Cancel
          </button>
          <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Adjusting...' : 'Adjust'}
          </button>
        </div>
      </form>
    </FormModal>
  );
}

import { createMilestone } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary } from '../../../constants/styles';
import { TextField, TextAreaField } from '../../../components/form';

export default function AddMilestoneModal({ projectId, onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: '',
    description: '',
    bonus_amount: '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createMilestone(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        bonus_amount: form.bonus_amount || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Milestone" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <TextField label="Title" value={form.title} onChange={onField('title')} required autoFocus />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <TextField label="Bonus ($)" value={form.bonus_amount} onChange={onField('bonus_amount')} type="number" step="0.01" min="0" placeholder="Optional" />
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Adding...' : 'Add Milestone'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

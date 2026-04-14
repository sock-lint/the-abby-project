import { createMilestone } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary, inputClass } from '../../../constants/styles';

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
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={onField('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea value={form.description} onChange={onField('description')} className={`${inputClass} h-16 resize-none`} />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Bonus ($)</label>
          <input value={form.bonus_amount} onChange={onField('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" placeholder="Optional" />
        </div>
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

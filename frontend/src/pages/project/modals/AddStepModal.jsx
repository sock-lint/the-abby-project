import { createStep } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary, inputClass } from '../../../constants/styles';

export default function AddStepModal({
  projectId, milestones = [], initialMilestoneId = null, onClose, onSaved,
}) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: '',
    description: '',
    milestone: initialMilestoneId == null ? '' : String(initialMilestoneId),
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createStep(projectId, {
        project: projectId,
        title: form.title,
        description: form.description,
        milestone: form.milestone === '' ? null : Number(form.milestone),
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Step" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <p className="text-xs text-forge-text-dim">
          Steps are walkthrough instructions — no coins, XP, or ledger impact.
        </p>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Title</label>
          <input value={form.title} onChange={onField('title')} className={inputClass} required autoFocus />
        </div>
        <div>
          <label className="block text-xs text-forge-text-dim mb-1">Description</label>
          <textarea
            value={form.description}
            onChange={onField('description')}
            className={`${inputClass} h-24 resize-none`}
            placeholder="What does the maker do next?"
          />
        </div>
        {milestones.length > 0 && (
          <div>
            <label className="block text-xs text-forge-text-dim mb-1">Milestone</label>
            <select value={form.milestone} onChange={onField('milestone')} className={inputClass}>
              <option value="">(No milestone — loose step)</option>
              {milestones.map((m, idx) => (
                <option key={m.id} value={m.id}>
                  {idx + 1}. {m.title || `Milestone ${idx + 1}`}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.title.trim()} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Adding...' : 'Add Step'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

import { createMaterial } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary } from '../../../constants/styles';
import { TextField, TextAreaField } from '../../../components/form';

export default function AddMaterialModal({ projectId, onClose, onSaved }) {
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: '',
    description: '',
    estimated_cost: '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await createMaterial(projectId, {
        project: projectId,
        name: form.name,
        description: form.description,
        estimated_cost: form.estimated_cost || '0',
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Add Material" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <TextField label="Name" value={form.name} onChange={onField('name')} required autoFocus />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <TextField label="Estimated Cost ($)" value={form.estimated_cost} onChange={onField('estimated_cost')} type="number" step="0.01" min="0" />
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving || !form.name.trim()} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Adding...' : 'Add Material'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

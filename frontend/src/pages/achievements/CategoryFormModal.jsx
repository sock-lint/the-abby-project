import { createCategory, updateCategory } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary } from '../../constants/styles';
import { TextField, TextAreaField } from '../../components/form';

export default function CategoryFormModal({ item, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: item?.name || '',
    icon: item?.icon || '',
    color: item?.color || '#D97706', // intentional: default value seeding the <input type="color"> picker — user-pickable color literal stored as data, not a surface token
    description: item?.description || '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      if (isEdit) await updateCategory(item.id, form);
      else await createCategory(form);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={isEdit ? 'Edit Category' : 'New Category'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon (emoji)" value={form.icon} onChange={onField('icon')} />
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Color</label>
            {/* Raw <input type="color"> stays — color picker has its own visual treatment, not inputClass-styled */}
            <input
              type="color"
              className="w-full h-10 rounded-lg border border-ink-page-shadow bg-ink-page cursor-pointer"
              value={form.color}
              onChange={onField('color')}
            />
          </div>
        </div>
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-whisper">Cancel</button>
          <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

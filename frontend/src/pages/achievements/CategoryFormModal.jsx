import { createCategory, updateCategory } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';

export default function CategoryFormModal({ item, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: item?.name || '',
    icon: item?.icon || '',
    color: item?.color || '#D97706',
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
    <FormModal title={isEdit ? 'Edit Category' : 'New Category'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Name</label>
          <input className={inputClass} value={form.name} onChange={onField('name')} required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Icon (emoji)</label>
            <input className={inputClass} value={form.icon} onChange={onField('icon')} />
          </div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Color</label>
            <input
              type="color"
              className="w-full h-10 rounded-lg border border-forge-border bg-forge-bg cursor-pointer"
              value={form.color}
              onChange={onField('color')}
            />
          </div>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
          <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-forge-text-dim">Cancel</button>
          <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </FormModal>
  );
}

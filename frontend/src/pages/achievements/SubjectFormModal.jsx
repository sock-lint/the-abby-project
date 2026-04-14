import { createSubject, updateSubject } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';

export default function SubjectFormModal({ item, categories, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: item?.name || '',
    category: item?.category || '',
    icon: item?.icon || '',
    description: item?.description || '',
    order: item?.order ?? 0,
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = {
        ...form,
        category: parseInt(form.category),
        order: parseInt(form.order) || 0,
      };
      if (isEdit) await updateSubject(item.id, payload);
      else await createSubject(payload);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormModal title={isEdit ? 'Edit Subject' : 'New Subject'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Name</label>
          <input className={inputClass} value={form.name} onChange={onField('name')} required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Category</label>
            <select className={inputClass} value={form.category} onChange={onField('category')} required>
              <option value="">Select...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-forge-text-dim mb-1 block">Icon</label>
            <input className={inputClass} value={form.icon} onChange={onField('icon')} />
          </div>
        </div>
        <div>
          <label className="text-xs text-forge-text-dim mb-1 block">Description</label>
          <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} />
        </div>
        <div className="w-1/2">
          <label className="text-xs text-forge-text-dim mb-1 block">Order</label>
          <input className={inputClass} type="number" value={form.order} onChange={onField('order')} />
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

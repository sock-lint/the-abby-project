import { createSkill, updateSkill } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import FormModal from '../../components/FormModal';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';

export default function SkillFormModal({ item, categories, subjects, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: item?.name || '',
    category: item?.category || '',
    subject: item?.subject || '',
    icon: item?.icon || '',
    description: item?.description || '',
    is_locked_by_default: item?.is_locked_by_default ?? false,
    order: item?.order ?? 0,
    level_names: JSON.stringify(item?.level_names || {}),
  });

  const onField = (k) => (e) => {
    const val = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    set({ [k]: val });
  };

  const filteredSubjects = subjects.filter(
    (s) => !form.category || s.category === parseInt(form.category),
  );

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      let level_names = {};
      try { level_names = JSON.parse(form.level_names); } catch { /* keep empty */ }
      const payload = {
        name: form.name,
        category: parseInt(form.category),
        subject: form.subject ? parseInt(form.subject) : null,
        icon: form.icon,
        description: form.description,
        is_locked_by_default: form.is_locked_by_default,
        order: parseInt(form.order) || 0,
        level_names,
      };
      if (isEdit) await updateSkill(item.id, payload);
      else await createSkill(payload);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <FormModal title={isEdit ? 'Edit Skill' : 'New Skill'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Name</label>
          <input className={inputClass} value={form.name} onChange={onField('name')} required />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Category</label>
            <select className={inputClass} value={form.category} onChange={onField('category')} required>
              <option value="">Select...</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Subject</label>
            <select className={inputClass} value={form.subject} onChange={onField('subject')}>
              <option value="">None</option>
              {filteredSubjects.map((s) => (
                <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Icon</label>
            <input className={inputClass} value={form.icon} onChange={onField('icon')} />
          </div>
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Order</label>
            <input className={inputClass} type="number" value={form.order} onChange={onField('order')} />
          </div>
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Description</label>
          <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} />
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Level Names (JSON)</label>
          <input
            className={inputClass}
            value={form.level_names}
            onChange={onField('level_names')}
            placeholder='{"0":"Novice","1":"Apprentice"}'
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.is_locked_by_default}
            onChange={onField('is_locked_by_default')}
            className="accent-amber-primary"
          />
          Locked by default
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-ink-whisper">Cancel</button>
          <button type="submit" disabled={saving} className={`px-4 py-2 text-sm ${buttonPrimary}`}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </button>
        </div>
      </form>
    </FormModal>
  );
}

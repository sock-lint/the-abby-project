import { createSkill, updateSkill } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import Button from '../../components/Button';
import { TextField, SelectField, TextAreaField } from '../../components/form';

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
    <BottomSheet title={isEdit ? 'Edit Skill' : 'New Skill'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Category" value={form.category} onChange={onField('category')} required>
            <option value="">Select...</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
            ))}
          </SelectField>
          <SelectField label="Subject" value={form.subject} onChange={onField('subject')}>
            <option value="">None</option>
            {filteredSubjects.map((s) => (
              <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
            ))}
          </SelectField>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TextField label="Icon" value={form.icon} onChange={onField('icon')} />
          <TextField label="Order" type="number" value={form.order} onChange={onField('order')} />
        </div>
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <TextField
          label="Level Names (JSON)"
          value={form.level_names}
          onChange={onField('level_names')}
          placeholder='{"0":"Novice","1":"Apprentice"}'
        />
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
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" disabled={saving}>
            {saving ? 'Saving...' : isEdit ? 'Update' : 'Create'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

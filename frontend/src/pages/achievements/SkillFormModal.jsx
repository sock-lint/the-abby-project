import { createSkill, updateSkill } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import Button from '../../components/Button';
import TaxonomyOptions from '../../components/form/TaxonomyOptions';
import { TextField, SelectField, TextAreaField, CheckboxField, IconPicker } from '../../components/form';

export default function SkillFormModal({ item, categories, subjects, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError, dirty } = useFormState({
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
    <BottomSheet title={isEdit ? 'Edit Skill' : 'New Skill'} onClose={onClose} dirty={dirty}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <TextField label="Name" value={form.name} onChange={onField('name')} required />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <SelectField label="Category" value={form.category} onChange={onField('category')} required>
            <option value="">Select...</option>
            <TaxonomyOptions entries={categories} selected={form.category} kind="category" />
          </SelectField>
          <SelectField label="Subject" value={form.subject} onChange={onField('subject')}>
            <option value="">None</option>
            <TaxonomyOptions entries={filteredSubjects} selected={form.subject} kind="subject" />
          </SelectField>
        </div>
        <IconPicker value={form.icon} placeholder="" onChange={(icon) => set({ icon })} disabled={saving} />
        <TextField className="sm:w-1/2" label="Order" type="number" value={form.order} onChange={onField('order')} />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={2} />
        <TextField
          label="Level Names (JSON)"
          value={form.level_names}
          onChange={onField('level_names')}
          placeholder='{"0":"Novice","1":"Apprentice"}'
        />
        <CheckboxField
          label="Locked by default"
          checked={form.is_locked_by_default}
          onChange={onField('is_locked_by_default')}
        />
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button type="submit" size="sm" loading={saving}>
            {isEdit ? 'Update' : 'Create'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

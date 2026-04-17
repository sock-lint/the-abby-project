import { getCategories, getChildren, updateProject } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useApi } from '../../../hooks/useApi';
import { useFormState } from '../../../hooks/useFormState';
import Button from '../../../components/Button';
import { TextField, SelectField, TextAreaField } from '../../../components/form';
import { normalizeList } from '../../../utils/api';

export default function EditProjectModal({ project, onClose, onSaved }) {
  const { data: categoriesData } = useApi(getCategories);
  const { data: childrenData } = useApi(getChildren);
  const categories = normalizeList(categoriesData);
  const children = normalizeList(childrenData);

  const { form, set, saving, setSaving, error, setError } = useFormState({
    title: project.title || '',
    description: project.description || '',
    difficulty: project.difficulty || 2,
    category_id: project.category?.id || '',
    assigned_to_id: project.assigned_to?.id || '',
    bonus_amount: project.bonus_amount || '0',
    payment_kind: project.payment_kind || 'required',
    hourly_rate_override: project.hourly_rate_override || '',
    materials_budget: project.materials_budget || '0',
    due_date: project.due_date || '',
    parent_notes: project.parent_notes || '',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await updateProject(project.id, {
        ...form,
        difficulty: parseInt(form.difficulty),
        category_id: form.category_id || null,
        assigned_to_id: form.assigned_to_id || null,
        hourly_rate_override: form.hourly_rate_override || null,
        due_date: form.due_date || null,
      });
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title="Edit Project" onClose={onClose} disabled={saving}>
      <form onSubmit={handleSubmit} className="space-y-3">
        <ErrorAlert message={error} />
        <TextField label="Title" value={form.title} onChange={onField('title')} required />
        <TextAreaField label="Description" value={form.description} onChange={onField('description')} rows={3} />
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Category" value={form.category_id} onChange={onField('category_id')}>
            <option value="">None</option>
            {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
          </SelectField>
          <SelectField label="Difficulty" value={form.difficulty} onChange={onField('difficulty')}>
            {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
          </SelectField>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <SelectField label="Assign To" value={form.assigned_to_id} onChange={onField('assigned_to_id')}>
            <option value="">Unassigned</option>
            {children.map((c) => (
              <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
            ))}
          </SelectField>
          <SelectField label="Payment Kind" value={form.payment_kind} onChange={onField('payment_kind')}>
            <option value="required">Required</option>
            <option value="bounty">Bounty</option>
          </SelectField>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <TextField
            label={form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
            value={form.bonus_amount}
            onChange={onField('bonus_amount')}
            type="number"
            step="0.01"
            min="0"
          />
          <TextField label="Budget ($)" value={form.materials_budget} onChange={onField('materials_budget')} type="number" step="0.01" min="0" />
          <TextField label="Rate Override ($)" value={form.hourly_rate_override} onChange={onField('hourly_rate_override')} type="number" step="0.01" min="0" placeholder="Default" />
        </div>
        <TextField label="Due Date" value={form.due_date} onChange={onField('due_date')} type="date" />
        <TextAreaField label="Parent Notes" value={form.parent_notes} onChange={onField('parent_notes')} rows={2} placeholder="Private notes" />
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose} disabled={saving} className="flex-1">
            Cancel
          </Button>
          <Button type="submit" disabled={saving} className="flex-1">
            {saving ? 'Saving...' : 'Save Changes'}
          </Button>
        </div>
      </form>
    </BottomSheet>
  );
}

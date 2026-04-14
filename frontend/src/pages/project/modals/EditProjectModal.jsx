import { getCategories, getChildren, updateProject } from '../../../api';
import BottomSheet from '../../../components/BottomSheet';
import ErrorAlert from '../../../components/ErrorAlert';
import { useApi } from '../../../hooks/useApi';
import { useFormState } from '../../../hooks/useFormState';
import { buttonPrimary, buttonSecondary, inputClass } from '../../../constants/styles';
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
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Title</label>
          <input value={form.title} onChange={onField('title')} className={inputClass} required />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Description</label>
          <textarea value={form.description} onChange={onField('description')} className={`${inputClass} h-20 resize-none`} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Category</label>
            <select value={form.category_id} onChange={onField('category_id')} className={inputClass}>
              <option value="">None</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Difficulty</label>
            <select value={form.difficulty} onChange={onField('difficulty')} className={inputClass}>
              {[1, 2, 3, 4, 5].map((d) => <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>)}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Assign To</label>
            <select value={form.assigned_to_id} onChange={onField('assigned_to_id')} className={inputClass}>
              <option value="">Unassigned</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.username}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Payment Kind</label>
            <select value={form.payment_kind} onChange={onField('payment_kind')} className={inputClass}>
              <option value="required">Required</option>
              <option value="bounty">Bounty</option>
            </select>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="block text-xs text-ink-whisper mb-1">
              {form.payment_kind === 'bounty' ? 'Bounty ($)' : 'Bonus ($)'}
            </label>
            <input value={form.bonus_amount} onChange={onField('bonus_amount')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Budget ($)</label>
            <input value={form.materials_budget} onChange={onField('materials_budget')} className={inputClass} type="number" step="0.01" min="0" />
          </div>
          <div>
            <label className="block text-xs text-ink-whisper mb-1">Rate Override ($)</label>
            <input value={form.hourly_rate_override} onChange={onField('hourly_rate_override')} className={inputClass} type="number" step="0.01" min="0" placeholder="Default" />
          </div>
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Due Date</label>
          <input value={form.due_date} onChange={onField('due_date')} className={inputClass} type="date" />
        </div>
        <div>
          <label className="block text-xs text-ink-whisper mb-1">Parent Notes</label>
          <textarea value={form.parent_notes} onChange={onField('parent_notes')} className={`${inputClass} h-16 resize-none`} placeholder="Private notes" />
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={onClose} disabled={saving} className={`flex-1 py-3 ${buttonSecondary}`}>
            Cancel
          </button>
          <button type="submit" disabled={saving} className={`flex-1 py-3 ${buttonPrimary}`}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </form>
    </BottomSheet>
  );
}

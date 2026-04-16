import { createBadge, updateBadge } from '../../api';
import ErrorAlert from '../../components/ErrorAlert';
import BottomSheet from '../../components/BottomSheet';
import { useFormState } from '../../hooks/useFormState';
import { buttonPrimary, inputClass } from '../../constants/styles';

const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary'];

const CRITERIA_TYPES = [
  'projects_completed', 'hours_worked', 'category_projects', 'streak_days',
  'first_project', 'first_clock_in', 'materials_under_budget', 'perfect_timecard',
  'skill_level_reached', 'skills_unlocked', 'skill_categories_breadth',
  'subjects_completed', 'hours_in_day', 'photos_uploaded', 'total_earned',
  'days_worked', 'cross_category_unlock',
];

export default function BadgeFormModal({ item, subjects, onClose, onSaved }) {
  const isEdit = !!item;
  const { form, set, saving, setSaving, error, setError } = useFormState({
    name: item?.name || '',
    description: item?.description || '',
    icon: item?.icon || '',
    subject: item?.subject || '',
    criteria_type: item?.criteria_type || CRITERIA_TYPES[0],
    criteria_value: JSON.stringify(item?.criteria_value || {}),
    xp_bonus: item?.xp_bonus ?? 0,
    rarity: item?.rarity || 'common',
  });

  const onField = (k) => (e) => set({ [k]: e.target.value });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      let criteria_value = {};
      try { criteria_value = JSON.parse(form.criteria_value); } catch { /* keep empty */ }
      const payload = {
        name: form.name,
        description: form.description,
        icon: form.icon,
        subject: form.subject ? parseInt(form.subject) : null,
        criteria_type: form.criteria_type,
        criteria_value,
        xp_bonus: parseInt(form.xp_bonus) || 0,
        rarity: form.rarity,
      };
      if (isEdit) await updateBadge(item.id, payload);
      else await createBadge(payload);
      onSaved();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <BottomSheet title={isEdit ? 'Edit Badge' : 'New Badge'} onClose={onClose}>
      <ErrorAlert message={error} />
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Name</label>
          <input className={inputClass} value={form.name} onChange={onField('name')} required />
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Description</label>
          <textarea className={inputClass} value={form.description} onChange={onField('description')} rows={2} required />
        </div>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Icon</label>
            <input className={inputClass} value={form.icon} onChange={onField('icon')} />
          </div>
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">Rarity</label>
            <select className={inputClass} value={form.rarity} onChange={onField('rarity')}>
              {RARITIES.map((r) => (
                <option key={r} value={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-ink-whisper mb-1 block">XP Bonus</label>
            <input className={inputClass} type="number" min="0" value={form.xp_bonus} onChange={onField('xp_bonus')} />
          </div>
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Subject (optional)</label>
          <select className={inputClass} value={form.subject} onChange={onField('subject')}>
            <option value="">None</option>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>{s.icon} {s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Criteria Type</label>
          <select className={inputClass} value={form.criteria_type} onChange={onField('criteria_type')}>
            {CRITERIA_TYPES.map((ct) => (
              <option key={ct} value={ct}>{ct.replace(/_/g, ' ')}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-ink-whisper mb-1 block">Criteria Value (JSON)</label>
          <input
            className={inputClass}
            value={form.criteria_value}
            onChange={onField('criteria_value')}
            placeholder='{"count": 5}'
          />
        </div>
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

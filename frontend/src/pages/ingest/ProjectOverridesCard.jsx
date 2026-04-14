import Card from '../../components/Card';
import { inputClass } from '../../constants/styles';

/**
 * The "Review & Edit" card — title/description from the parsed draft, plus
 * project-level overrides (category, difficulty, bonus, budget, due date)
 * that are applied at commit time.
 */
export default function ProjectOverridesCard({
  draft, setDraft,
  overrides, setOverrides,
  categories,
}) {
  const setOverride = (k) => (e) => setOverrides({ ...overrides, [k]: e.target.value });

  return (
    <Card className="space-y-4">
      <h2 className="font-heading text-lg font-bold">Review &amp; Edit</h2>

      {draft.cover_photo_url && (
        <img src={draft.cover_photo_url} alt="" className="w-full h-40 object-cover rounded-lg" />
      )}

      <div>
        <label className="block text-sm text-forge-text-dim mb-1">Title</label>
        <input
          value={draft.title || ''}
          onChange={(e) => setDraft({ ...draft, title: e.target.value })}
          className={inputClass}
        />
      </div>
      <div>
        <label className="block text-sm text-forge-text-dim mb-1">Description</label>
        <textarea
          value={draft.description || ''}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          className={`${inputClass} h-20 resize-none`}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Category</label>
          <select value={overrides.category_id} onChange={setOverride('category_id')} className={inputClass}>
            <option value="">
              {draft.category_hint ? `Suggested: ${draft.category_hint}` : 'None'}
            </option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Difficulty</label>
          <select value={overrides.difficulty} onChange={setOverride('difficulty')} className={inputClass}>
            {[1, 2, 3, 4, 5].map((d) => (
              <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Bonus ($)</label>
          <input
            value={overrides.bonus_amount}
            onChange={setOverride('bonus_amount')}
            className={inputClass}
            type="number" step="0.01" min="0" inputMode="decimal"
          />
        </div>
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Materials Budget ($)</label>
          <input
            value={overrides.materials_budget}
            onChange={setOverride('materials_budget')}
            className={inputClass}
            type="number" step="0.01" min="0" inputMode="decimal"
          />
        </div>
        <div>
          <label className="block text-sm text-forge-text-dim mb-1">Due Date</label>
          <input
            value={overrides.due_date}
            onChange={setOverride('due_date')}
            className={inputClass}
            type="date"
          />
        </div>
      </div>
    </Card>
  );
}

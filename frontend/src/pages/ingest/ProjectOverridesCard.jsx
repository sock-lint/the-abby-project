import ParchmentCard from '../../components/journal/ParchmentCard';
import { TextField, SelectField, TextAreaField } from '../../components/form';

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
    <ParchmentCard className="space-y-4">
      <h2 className="font-display text-lg font-bold">Review &amp; Edit</h2>

      {draft.cover_photo_url && (
        <img src={draft.cover_photo_url} alt="" className="w-full h-40 object-cover rounded-lg" />
      )}

      <TextField
        label="Title"
        value={draft.title || ''}
        onChange={(e) => setDraft({ ...draft, title: e.target.value })}
      />
      <TextAreaField
        label="Description"
        value={draft.description || ''}
        onChange={(e) => setDraft({ ...draft, description: e.target.value })}
        rows={3}
      />

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <SelectField label="Category" value={overrides.category_id} onChange={setOverride('category_id')}>
          <option value="">
            {draft.category_hint ? `Suggested: ${draft.category_hint}` : 'None'}
          </option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>{c.icon} {c.name}</option>
          ))}
        </SelectField>
        <SelectField label="Difficulty" value={overrides.difficulty} onChange={setOverride('difficulty')}>
          {[1, 2, 3, 4, 5].map((d) => (
            <option key={d} value={d}>{'\u2605'.repeat(d)} ({d})</option>
          ))}
        </SelectField>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <TextField
          label="Bonus ($)"
          value={overrides.bonus_amount}
          onChange={setOverride('bonus_amount')}
          type="number" step="0.01" min="0" inputMode="decimal"
        />
        <TextField
          label="Materials Budget ($)"
          value={overrides.materials_budget}
          onChange={setOverride('materials_budget')}
          type="number" step="0.01" min="0" inputMode="decimal"
        />
        <TextField
          label="Due Date"
          value={overrides.due_date}
          onChange={setOverride('due_date')}
          type="date"
        />
      </div>
    </ParchmentCard>
  );
}

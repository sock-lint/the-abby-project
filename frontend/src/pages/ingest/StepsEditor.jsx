import { Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { inputClass } from '../../constants/styles';

export default function StepsEditor({ steps, milestones, onAdd, onUpdate, onRemove }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-bold">Steps ({steps.length})</h2>
        <button onClick={onAdd} className="text-xs text-sheikah-teal-deep hover:text-sheikah-teal-deep flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      <p className="text-xs text-ink-whisper">
        Ordered walkthrough instructions. Assign a step to a milestone above to group it under that chapter — leave loose if it's a one-off.
      </p>
      {steps.length === 0 && (
        <div className="text-xs text-ink-whisper italic">
          No walkthrough steps parsed. Add some manually or accept an AI suggestion above.
        </div>
      )}
      {steps.map((s, i) => (
        <div key={`s-${i}`} className="bg-ink-page border border-ink-page-shadow rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <input
              value={s.title}
              onChange={(e) => onUpdate(i, { title: e.target.value })}
              className={inputClass}
              placeholder={`Step ${i + 1}`}
            />
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label="Remove step"
              className="text-ink-whisper hover:text-ember-deep shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
            >
              <Trash2 size={18} />
            </button>
          </div>
          <textarea
            value={s.description || ''}
            onChange={(e) => onUpdate(i, { description: e.target.value })}
            className={`${inputClass} h-20 resize-none text-xs`}
            placeholder="What does the maker do in this step?"
          />
          {milestones.length > 0 && (
            <select
              value={s.milestone_index == null ? '' : String(s.milestone_index)}
              onChange={(e) =>
                onUpdate(i, {
                  milestone_index: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
              className={`${inputClass} text-xs`}
            >
              <option value="">(No milestone — loose step)</option>
              {milestones.map((m, idx) => (
                <option key={idx} value={idx}>
                  {idx + 1}. {(m.title || '').slice(0, 30) || `Milestone ${idx + 1}`}
                </option>
              ))}
            </select>
          )}
        </div>
      ))}
    </Card>
  );
}

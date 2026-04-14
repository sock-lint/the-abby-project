import { Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { inputClass } from '../../constants/styles';

export default function MilestonesEditor({ milestones, onAdd, onUpdate, onRemove }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg font-bold">Milestones ({milestones.length})</h2>
        <button onClick={onAdd} className="text-xs text-amber-primary hover:text-amber-highlight flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      <p className="text-xs text-forge-text-dim">
        Optional payment goals — chapters of the project. Each one can hold a $ bonus and group its own steps below.
      </p>
      {milestones.map((m, i) => (
        <div key={i} className="bg-forge-bg border border-forge-border rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <input
              value={m.title}
              onChange={(e) => onUpdate(i, { title: e.target.value })}
              className={inputClass}
              placeholder={`Milestone ${i + 1}`}
            />
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label="Remove milestone"
              className="text-forge-text-dim hover:text-red-400 shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
            >
              <Trash2 size={18} />
            </button>
          </div>
          <textarea
            value={m.description || ''}
            onChange={(e) => onUpdate(i, { description: e.target.value })}
            className={`${inputClass} h-16 resize-none text-xs`}
            placeholder="Description (optional)"
          />
        </div>
      ))}
    </Card>
  );
}

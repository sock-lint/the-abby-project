import { Plus, Trash2 } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { TextField, TextAreaField } from '../../components/form';

export default function MilestonesEditor({ milestones, onAdd, onUpdate, onRemove }) {
  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-bold">Milestones ({milestones.length})</h2>
        <button onClick={onAdd} className="text-xs text-sheikah-teal-deep hover:text-sheikah-teal-deep flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      <p className="text-xs text-ink-whisper">
        Optional payment goals — chapters of the project. Each one can hold a $ bonus and group its own steps below.
      </p>
      {milestones.map((m, i) => (
        <div key={i} className="bg-ink-page border border-ink-page-shadow rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <TextField
              className="flex-1"
              value={m.title}
              onChange={(e) => onUpdate(i, { title: e.target.value })}
              placeholder={`Milestone ${i + 1}`}
            />
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label="Remove milestone"
              className="text-ink-whisper hover:text-ember-deep shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
            >
              <Trash2 size={18} />
            </button>
          </div>
          <TextAreaField
            value={m.description || ''}
            onChange={(e) => onUpdate(i, { description: e.target.value })}
            rows={2}
            placeholder="Description (optional)"
          />
        </div>
      ))}
    </ParchmentCard>
  );
}

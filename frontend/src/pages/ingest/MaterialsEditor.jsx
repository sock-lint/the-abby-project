import { Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { inputClass } from '../../constants/styles';

export default function MaterialsEditor({ materials, onAdd, onUpdate, onRemove }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-bold">Materials ({materials.length})</h2>
        <button onClick={onAdd} className="text-xs text-sheikah-teal-deep hover:text-sheikah-teal-deep flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      {materials.map((m, i) => (
        <div key={i} className="flex gap-2">
          <input
            value={m.name}
            onChange={(e) => onUpdate(i, { name: e.target.value })}
            className={`${inputClass} flex-1`}
            placeholder="Material name"
          />
          <input
            value={m.estimated_cost ?? ''}
            onChange={(e) => onUpdate(i, { estimated_cost: e.target.value })}
            className={`${inputClass} w-24`}
            type="number" step="0.01" min="0" inputMode="decimal"
            placeholder="$ est."
          />
          <button
            type="button"
            onClick={() => onRemove(i)}
            aria-label="Remove material"
            className="text-ink-whisper hover:text-ember-deep shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
          >
            <Trash2 size={18} />
          </button>
        </div>
      ))}
    </Card>
  );
}

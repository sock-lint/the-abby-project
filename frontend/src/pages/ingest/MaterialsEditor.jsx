import { Plus, Trash2 } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { TextField } from '../../components/form';

export default function MaterialsEditor({ materials, onAdd, onUpdate, onRemove }) {
  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="font-display text-lg font-bold">Materials ({materials.length})</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onAdd}
          className="flex items-center gap-1 !text-sheikah-teal-deep hover:!text-sheikah-teal"
        >
          <Plus size={14} /> Add
        </Button>
      </div>
      {materials.map((m, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_6rem_auto] gap-2 items-start">
          <TextField
            className="min-w-0"
            aria-label={`Material ${i + 1} name`}
            value={m.name}
            onChange={(e) => onUpdate(i, { name: e.target.value })}
            placeholder="Material name"
          />
          <TextField
            className="min-w-0 col-start-1 row-start-2 sm:col-start-2 sm:row-start-1"
            aria-label={`Material ${i + 1} estimated cost`}
            value={m.estimated_cost ?? ''}
            onChange={(e) => onUpdate(i, { estimated_cost: e.target.value })}
            type="number" step="0.01" min="0" inputMode="decimal"
            placeholder="$ est."
          />
          <IconButton
            onClick={() => onRemove(i)}
            aria-label="Remove material"
            className="col-start-2 row-start-1 sm:col-start-3 text-ink-whisper hover:text-ember-deep"
          >
            <Trash2 size={18} />
          </IconButton>
        </div>
      ))}
    </ParchmentCard>
  );
}

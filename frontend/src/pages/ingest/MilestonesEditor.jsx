import { Plus, Trash2 } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { TextField, TextAreaField } from '../../components/form';

export default function MilestonesEditor({ milestones, onAdd, onUpdate, onRemove }) {
  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="font-display text-lg font-bold">Milestones ({milestones.length})</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onAdd}
          className="flex items-center gap-1 !text-sheikah-teal-deep hover:!text-sheikah-teal"
        >
          <Plus size={14} /> Add
        </Button>
      </div>
      <p className="text-caption text-ink-whisper">
        Group steps into milestones. Each milestone can include an optional cash bonus.
      </p>
      {milestones.map((m, i) => (
        <div key={i} className="bg-ink-page border border-ink-page-shadow rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <TextField
              className="flex-1 min-w-0"
              aria-label={`Milestone ${i + 1} title`}
              value={m.title}
              onChange={(e) => onUpdate(i, { title: e.target.value })}
              placeholder={`Milestone ${i + 1}`}
            />
            <IconButton
              onClick={() => onRemove(i)}
              aria-label="Remove milestone"
              className="text-ink-whisper hover:text-ember-deep shrink-0"
            >
              <Trash2 size={18} />
            </IconButton>
          </div>
          <TextAreaField
            aria-label={`Milestone ${i + 1} description`}
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

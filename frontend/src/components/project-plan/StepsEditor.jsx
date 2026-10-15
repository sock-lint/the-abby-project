import { Plus, Trash2 } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import Button from '../Button';
import IconButton from '../IconButton';
import { TextField, SelectField, TextAreaField } from '../form';

export default function StepsEditor({ steps, milestones, onAdd, onUpdate, onRemove, maxItems = Infinity, titleLimit, descriptionLimit }) {
  return (
    <ParchmentCard className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <h2 className="font-display text-lg font-bold">Steps ({steps.length})</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={onAdd}
          disabled={steps.length >= maxItems}
          className="flex items-center gap-1 !text-sheikah-teal-deep hover:!text-sheikah-teal"
        >
          <Plus size={14} /> Add
        </Button>
      </div>
      <p className="text-caption text-ink-whisper">
        Add the instructions in order. Assign each step to a milestone, or leave it ungrouped.
      </p>
      {steps.length === 0 && (
        <div className="text-caption text-ink-whisper italic">
          No walkthrough steps parsed. Add some manually or accept an AI suggestion above.
        </div>
      )}
      {steps.map((s, i) => (
        <div key={`s-${i}`} className="bg-ink-page border border-ink-page-shadow rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <TextField
              className="flex-1 min-w-0"
              aria-label={`Step ${i + 1} title`}
              value={s.title}
              maxLength={titleLimit}
              onChange={(e) => onUpdate(i, { title: e.target.value })}
              placeholder={`Step ${i + 1}`}
            />
            <IconButton
              onClick={() => onRemove(i)}
              aria-label="Remove step"
              className="text-ink-whisper hover:text-ember-deep shrink-0"
            >
              <Trash2 size={18} />
            </IconButton>
          </div>
          <TextAreaField
            aria-label={`Step ${i + 1} description`}
            value={s.description || ''}
            maxLength={descriptionLimit}
            onChange={(e) => onUpdate(i, { description: e.target.value })}
            rows={3}
            placeholder="What does the maker do in this step?"
          />
          {milestones.length > 0 && (
            <SelectField
              aria-label={`Step ${i + 1} milestone`}
              value={s.milestone_index == null ? '' : String(s.milestone_index)}
              onChange={(e) =>
                onUpdate(i, {
                  milestone_index: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
            >
              <option value="">(No milestone — loose step)</option>
              {milestones.map((m, idx) => (
                <option key={idx} value={idx}>
                  {idx + 1}. {(m.title || '').slice(0, 30) || `Milestone ${idx + 1}`}
                </option>
              ))}
            </SelectField>
          )}
        </div>
      ))}
    </ParchmentCard>
  );
}

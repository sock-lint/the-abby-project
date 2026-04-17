import { Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { TextField, SelectField } from '../../components/form';

export default function ResourcesEditor({ resources, steps, onAdd, onUpdate, onRemove }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-lg font-bold">Resources ({resources.length})</h2>
        <button onClick={onAdd} className="text-xs text-sheikah-teal-deep hover:text-sheikah-teal-deep flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      <p className="text-xs text-ink-whisper">
        Reference videos, docs, or inspiration links. Attach to a step or leave project-level.
      </p>
      {resources.map((r, i) => (
        <div key={`r-${i}`} className="bg-ink-page border border-ink-page-shadow rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <TextField
              className="flex-1"
              value={r.url}
              onChange={(e) => onUpdate(i, { url: e.target.value })}
              type="url"
              placeholder="https://..."
            />
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label="Remove resource"
              className="text-ink-whisper hover:text-ember-deep shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
            >
              <Trash2 size={18} />
            </button>
          </div>
          <TextField
            value={r.title || ''}
            onChange={(e) => onUpdate(i, { title: e.target.value })}
            placeholder="Title (optional)"
          />
          <div className="flex gap-2">
            <SelectField
              className="flex-1"
              value={r.resource_type || 'link'}
              onChange={(e) => onUpdate(i, { resource_type: e.target.value })}
            >
              <option value="link">Link</option>
              <option value="video">Video</option>
              <option value="doc">Document</option>
              <option value="image">Image</option>
            </SelectField>
            <SelectField
              className="flex-1"
              value={r.step_index == null ? '' : String(r.step_index)}
              onChange={(e) =>
                onUpdate(i, {
                  step_index: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
            >
              <option value="">(Project-level)</option>
              {steps.map((s, idx) => (
                <option key={idx} value={idx}>
                  {idx + 1}. {(s.title || '').slice(0, 30) || `Step ${idx + 1}`}
                </option>
              ))}
            </SelectField>
          </div>
        </div>
      ))}
    </Card>
  );
}

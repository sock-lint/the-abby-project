import { Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import { inputClass } from '../../constants/styles';

export default function ResourcesEditor({ resources, steps, onAdd, onUpdate, onRemove }) {
  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-heading text-lg font-bold">Resources ({resources.length})</h2>
        <button onClick={onAdd} className="text-xs text-amber-primary hover:text-amber-highlight flex items-center gap-1">
          <Plus size={14} /> Add
        </button>
      </div>
      <p className="text-xs text-forge-text-dim">
        Reference videos, docs, or inspiration links. Attach to a step or leave project-level.
      </p>
      {resources.map((r, i) => (
        <div key={`r-${i}`} className="bg-forge-bg border border-forge-border rounded-lg p-3 space-y-2">
          <div className="flex gap-2">
            <input
              value={r.url}
              onChange={(e) => onUpdate(i, { url: e.target.value })}
              className={inputClass}
              type="url"
              placeholder="https://..."
            />
            <button
              type="button"
              onClick={() => onRemove(i)}
              aria-label="Remove resource"
              className="text-forge-text-dim hover:text-red-400 shrink-0 min-h-10 min-w-10 flex items-center justify-center rounded-lg"
            >
              <Trash2 size={18} />
            </button>
          </div>
          <input
            value={r.title || ''}
            onChange={(e) => onUpdate(i, { title: e.target.value })}
            className={`${inputClass} text-xs`}
            placeholder="Title (optional)"
          />
          <div className="flex gap-2">
            <select
              value={r.resource_type || 'link'}
              onChange={(e) => onUpdate(i, { resource_type: e.target.value })}
              className={`${inputClass} text-xs`}
            >
              <option value="link">Link</option>
              <option value="video">Video</option>
              <option value="doc">Document</option>
              <option value="image">Image</option>
            </select>
            <select
              value={r.step_index == null ? '' : String(r.step_index)}
              onChange={(e) =>
                onUpdate(i, {
                  step_index: e.target.value === '' ? null : parseInt(e.target.value, 10),
                })
              }
              className={`${inputClass} text-xs`}
            >
              <option value="">(Project-level)</option>
              {steps.map((s, idx) => (
                <option key={idx} value={idx}>
                  {idx + 1}. {(s.title || '').slice(0, 30) || `Step ${idx + 1}`}
                </option>
              ))}
            </select>
          </div>
        </div>
      ))}
    </Card>
  );
}

import { Check, Plus, Trash2 } from 'lucide-react';
import EmptyState from '../../components/EmptyState';
import ParchmentCard from '../../components/journal/ParchmentCard';

export default function MaterialsTab({
  project, isParent,
  onMarkPurchased, onDeleteMaterial,
  onOpenAddMaterial,
}) {
  const materials = project.materials || [];
  const spent = materials.reduce(
    (s, m) => s + parseFloat(m.actual_cost || m.estimated_cost || 0),
    0,
  );
  const budget = parseFloat(project.materials_budget || 1);
  const percent = Math.min(100, (spent / budget) * 100);

  return (
    <div className="space-y-2">
      {isParent && (
        <button
          type="button"
          onClick={onOpenAddMaterial}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border-2 border-dashed border-ink-page-shadow font-script text-sm text-ink-secondary hover:text-ink-primary hover:border-sheikah-teal/60 transition-colors"
        >
          <Plus size={16} /> add material
        </button>
      )}

      {materials.length > 0 && (
        <ParchmentCard className="mb-3">
          <div className="flex justify-between font-body text-sm">
            <span className="font-script text-ink-whisper uppercase tracking-wider">
              materials budget
            </span>
            <span className="font-rune font-bold text-ink-primary tabular-nums">
              ${project.materials_budget}
            </span>
          </div>
          <div className="h-2 bg-ink-page-shadow/60 rounded-full mt-2 overflow-hidden">
            <div
              className={`h-full rounded-full ${
                percent > 100 ? 'bg-ember' : 'bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal'
              }`}
              style={{ width: `${percent}%` }}
            />
          </div>
          <div className="font-script text-xs text-ink-whisper mt-1 text-right">
            spent ${spent.toFixed(2)}
          </div>
        </ParchmentCard>
      )}

      {materials.length === 0 && (
        <EmptyState className="py-8">No materials listed.</EmptyState>
      )}

      {materials.map((mat) => (
        <ParchmentCard key={mat.id} className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="font-body font-medium text-sm text-ink-primary">{mat.name}</div>
            <div className="font-script text-xs text-ink-whisper">
              est: ${mat.estimated_cost}
              {mat.actual_cost && <> · actual: ${mat.actual_cost}</>}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {mat.is_purchased ? (
              <span className="font-script text-xs text-moss flex items-center gap-1">
                <Check size={14} /> purchased
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onMarkPurchased(mat.id, mat.estimated_cost)}
                className="font-body text-xs bg-ink-page border border-ink-page-shadow hover:border-sheikah-teal/60 px-3 py-1 rounded-lg text-ink-primary transition-colors"
              >
                Mark purchased
              </button>
            )}
            {isParent && (
              <button
                type="button"
                onClick={() => onDeleteMaterial(mat.id)}
                aria-label="Delete material"
                className="text-ink-secondary hover:text-ember-deep p-1 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </ParchmentCard>
      ))}
    </div>
  );
}

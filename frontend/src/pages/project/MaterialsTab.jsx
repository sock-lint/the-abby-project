import { Check, Plus, Trash2 } from 'lucide-react';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
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
        <Button
          type="button"
          variant="secondary"
          onClick={onOpenAddMaterial}
          className="w-full flex items-center justify-center gap-2 py-2.5 border-2 border-dashed !bg-transparent hover:!bg-ink-page-aged/40 border-ink-page-shadow hover:border-sheikah-teal/60 font-script text-body text-ink-secondary hover:text-ink-primary"
        >
          <Plus size={16} /> add material
        </Button>
      )}

      {materials.length > 0 && (
        <ParchmentCard className="mb-3">
          <div className="flex justify-between font-body text-body">
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
          <div className="font-script text-tiny text-ink-whisper mt-1 text-right">
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
            <div className="font-body font-medium text-body text-ink-primary">{mat.name}</div>
            <div className="font-script text-tiny text-ink-whisper">
              est: ${mat.estimated_cost}
              {mat.actual_cost && <> · actual: ${mat.actual_cost}</>}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {mat.is_purchased ? (
              <span className="font-script text-tiny text-moss flex items-center gap-1">
                <Check size={14} /> purchased
              </span>
            ) : (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => onMarkPurchased(mat.id, mat.estimated_cost)}
              >
                Mark purchased
              </Button>
            )}
            {isParent && (
              <IconButton
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => onDeleteMaterial(mat.id)}
                aria-label="Delete material"
                className="text-ink-secondary hover:text-ember-deep"
              >
                <Trash2 size={14} />
              </IconButton>
            )}
          </div>
        </ParchmentCard>
      ))}
    </div>
  );
}

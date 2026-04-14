import { Check, Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import EmptyState from '../../components/EmptyState';

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
          onClick={onOpenAddMaterial}
          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
        >
          <Plus size={16} /> Add Material
        </button>
      )}

      {materials.length > 0 && (
        <Card className="mb-3">
          <div className="flex justify-between text-sm">
            <span className="text-forge-text-dim">Budget</span>
            <span className="font-heading font-bold">${project.materials_budget}</span>
          </div>
          <div className="h-2 bg-forge-muted rounded-full mt-2 overflow-hidden">
            <div
              className="h-full bg-amber-primary rounded-full"
              style={{ width: `${percent}%` }}
            />
          </div>
        </Card>
      )}

      {materials.length === 0 && <EmptyState className="py-8">No materials</EmptyState>}

      {materials.map((mat) => (
        <Card key={mat.id} className="flex items-center justify-between">
          <div>
            <div className="font-medium text-sm">{mat.name}</div>
            <div className="text-xs text-forge-text-dim">
              Est: ${mat.estimated_cost}
              {mat.actual_cost && ` | Actual: $${mat.actual_cost}`}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {mat.is_purchased ? (
              <span className="text-xs text-green-400 flex items-center gap-1">
                <Check size={14} /> Purchased
              </span>
            ) : (
              <button
                onClick={() => onMarkPurchased(mat.id, mat.estimated_cost)}
                className="text-xs bg-forge-muted hover:bg-forge-border px-3 py-1 rounded-lg transition-colors"
              >
                Mark Purchased
              </button>
            )}
            {isParent && (
              <button
                onClick={() => onDeleteMaterial(mat.id)}
                className="text-forge-text-dim hover:text-red-400 p-1 transition-colors"
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}

import MilestonesEditor from './MilestonesEditor';
import StepsEditor from './StepsEditor';
import MaterialsEditor from './MaterialsEditor';
import { PLAN_LIMITS, removePlanMilestone } from './projectPlan';

export default function PlanDraftEditor({ plan, onChange, disabled = false }) {
  const update = (key, index, patch) => onChange({ ...plan,
    [key]: plan[key].map((item, current) => current === index ? { ...item, ...patch } : item),
  });
  const add = (key, item) => {
    if (plan[key].length < PLAN_LIMITS[key]) onChange({ ...plan, [key]: [...plan[key], item] });
  };
  const remove = (key, index) => onChange({ ...plan, [key]: plan[key].filter((_, current) => current !== index) });
  const limits = { titleLimit: PLAN_LIMITS.title, descriptionLimit: PLAN_LIMITS.description };
  return (
    <fieldset disabled={disabled} className="min-w-0 space-y-3">
      <legend className="font-body font-semibold text-ink-primary mb-2">Review plan</legend>
      <p className="text-caption text-ink-secondary">Edit or remove any suggestion before saving. Milestone bonuses and project payments stay under your control.</p>
      <MilestonesEditor {...limits} milestones={plan.milestones} maxItems={PLAN_LIMITS.milestones}
        onAdd={() => add('milestones', { title: '', description: '' })}
        onUpdate={(index, patch) => update('milestones', index, patch)}
        onRemove={(index) => onChange(removePlanMilestone(plan, index))} />
      <StepsEditor {...limits} steps={plan.steps} milestones={plan.milestones} maxItems={PLAN_LIMITS.steps}
        onAdd={() => add('steps', { title: '', description: '', milestone_index: null })}
        onUpdate={(index, patch) => update('steps', index, patch)} onRemove={(index) => remove('steps', index)} />
      <MaterialsEditor {...limits} materials={plan.materials} showDescription maxItems={PLAN_LIMITS.materials}
        onAdd={() => add('materials', { name: '', description: '', estimated_cost: '0.00' })}
        onUpdate={(index, patch) => update('materials', index, patch)} onRemove={(index) => remove('materials', index)} />
    </fieldset>
  );
}

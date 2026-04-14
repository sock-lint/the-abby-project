import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Check, ChevronDown, DollarSign, Plus, Trash2 } from 'lucide-react';
import Card from '../../components/Card';
import EmptyState from '../../components/EmptyState';
import ProgressBar from '../../components/ProgressBar';
import { ResourcePill, StepCard } from './ProjectPlanItems';

const LOOSE_KEY = '__loose__';

export default function PlanTab({
  project, isParent,
  onCompleteMilestone, onDeleteMilestone,
  onToggleStep, onDeleteStep, onMoveStep,
  onDeleteResource,
  onOpenAddMilestone, onOpenAddStep, onOpenAddResource,
}) {
  const [collapsedMilestones, setCollapsedMilestones] = useState(() => new Set());

  const milestones = project.milestones || [];
  const { steps } = project;

  const stepsByMilestone = useMemo(() => {
    const map = new Map();
    for (const s of steps || []) {
      const key = s.milestone ?? LOOSE_KEY;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(s);
    }
    return map;
  }, [steps]);

  const looseSteps = stepsByMilestone.get(LOOSE_KEY) || [];

  const toggleMilestone = (msId) => {
    setCollapsedMilestones((prev) => {
      const next = new Set(prev);
      if (next.has(msId)) next.delete(msId);
      else next.add(msId);
      return next;
    });
  };

  return (
    <div className="space-y-3">
      {isParent && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={onOpenAddMilestone}
            className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
          >
            <Plus size={16} /> Add Milestone
          </button>
          <button
            onClick={() => onOpenAddStep(null)}
            className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
          >
            <Plus size={16} /> Add Step
          </button>
          <button
            onClick={onOpenAddResource}
            className="flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg border border-dashed border-forge-border text-sm text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
          >
            <Plus size={16} /> Add Resource
          </button>
        </div>
      )}

      {milestones.length === 0 && (project.steps || []).length === 0 && (
        <EmptyState className="py-8">
          No plan yet — add a milestone or a step to break this project down.
        </EmptyState>
      )}

      {/* Milestones with their nested steps. */}
      {milestones.map((ms) => {
        const childSteps = stepsByMilestone.get(ms.id) || [];
        const done = childSteps.filter((s) => s.is_completed).length;
        const total = childSteps.length;
        const collapsed = collapsedMilestones.has(ms.id);
        const allDone = total > 0 && done === total;
        return (
          <motion.div key={ms.id} layout>
            <Card className={ms.is_completed ? 'opacity-60' : ''}>
              <div className="flex items-start gap-3">
                <button
                  onClick={() => !ms.is_completed && onCompleteMilestone(ms.id)}
                  disabled={ms.is_completed}
                  aria-label={ms.is_completed ? 'Milestone completed' : 'Mark milestone complete'}
                  className={`w-6 h-6 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-colors ${
                    ms.is_completed
                      ? 'bg-green-500 border-green-500'
                      : 'border-forge-muted hover:border-amber-primary'
                  }`}
                >
                  {ms.is_completed && <Check size={14} className="text-white" />}
                </button>
                <button
                  onClick={() => toggleMilestone(ms.id)}
                  className="flex-1 min-w-0 text-left"
                >
                  <div className="flex items-center gap-2">
                    <div className={`font-heading font-bold text-sm ${ms.is_completed ? 'line-through' : ''}`}>
                      {ms.title}
                    </div>
                    {ms.bonus_amount && (
                      <span className="text-xs text-green-400 flex items-center gap-0.5">
                        <DollarSign size={12} />{ms.bonus_amount}
                      </span>
                    )}
                    <ChevronDown
                      size={14}
                      className={`text-forge-text-dim ml-auto transition-transform ${collapsed ? '-rotate-90' : ''}`}
                    />
                  </div>
                  {ms.description && (
                    <div className="text-xs text-forge-text-dim mt-0.5">{ms.description}</div>
                  )}
                  {total > 0 && (
                    <div className="mt-2 flex items-center gap-2">
                      <ProgressBar value={done} max={total} className="flex-1" />
                      <span className="text-[10px] text-forge-text-dim shrink-0">
                        {done}/{total}
                      </span>
                    </div>
                  )}
                </button>
                {isParent && (
                  <button
                    onClick={() => onDeleteMilestone(ms.id)}
                    className="text-forge-text-dim hover:text-red-400 p-1 transition-colors shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>

              {!collapsed && (
                <div className="mt-3 ml-9 space-y-2">
                  {allDone && !ms.is_completed && (
                    <button
                      onClick={() => onCompleteMilestone(ms.id)}
                      className="w-full text-xs bg-amber-primary/15 hover:bg-amber-primary/25 text-amber-highlight border border-amber-primary/30 rounded-lg py-2 transition-colors"
                    >
                      All steps done — mark milestone complete?
                    </button>
                  )}
                  {childSteps.map((step) => (
                    <StepCard
                      key={step.id}
                      step={step}
                      isParent={isParent}
                      milestones={milestones}
                      onToggle={onToggleStep}
                      onDelete={onDeleteStep}
                      onMove={onMoveStep}
                    />
                  ))}
                  {childSteps.length === 0 && (
                    <div className="text-xs text-forge-text-dim italic">
                      No steps in this milestone yet.
                    </div>
                  )}
                  {isParent && (
                    <button
                      onClick={() => onOpenAddStep(ms.id)}
                      className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-dashed border-forge-border text-xs text-forge-text-dim hover:text-forge-text hover:border-amber-primary transition-colors"
                    >
                      <Plus size={12} /> Add step here
                    </button>
                  )}
                </div>
              )}
            </Card>
          </motion.div>
        );
      })}

      {/* Loose / unassigned steps. When there are no milestones, this is
          the only section and acts as a flat step list (current behavior). */}
      {looseSteps.length > 0 && (
        <div className="space-y-2">
          {milestones.length > 0 && (
            <div className="text-xs text-forge-text-dim font-medium uppercase tracking-wide pt-2">
              Other Steps
            </div>
          )}
          {looseSteps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
              isParent={isParent}
              milestones={milestones}
              onToggle={onToggleStep}
              onDelete={onDeleteStep}
              onMove={onMoveStep}
            />
          ))}
        </div>
      )}

      {isParent && project.resources?.length > 0 && (
        <div className="pt-4">
          <div className="text-xs text-forge-text-dim mb-2 font-medium uppercase tracking-wide">
            Project-level Resources
          </div>
          <div className="space-y-1.5">
            {project.resources.map((r) => (
              <Card key={r.id} className="flex items-center justify-between py-2">
                <ResourcePill resource={r} />
                <button
                  onClick={() => onDeleteResource(r.id)}
                  className="text-forge-text-dim hover:text-red-400 p-1 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Check, ChevronDown, DollarSign, Plus, Trash2 } from 'lucide-react';
import EmptyState from '../../components/EmptyState';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { chapterMark } from '../../components/atlas/mastery.constants';
import { ResourcePill, StepCard } from './ProjectPlanItems';

const LOOSE_KEY = '__loose__';

const addButtonClass =
  'flex-1 min-w-[140px] flex items-center justify-center gap-2 py-2.5 rounded-lg ' +
  'border-2 border-dashed border-ink-page-shadow text-sm font-script ' +
  'text-ink-secondary hover:text-ink-primary hover:border-sheikah-teal/60 transition-colors';

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
          <button type="button" onClick={onOpenAddMilestone} className={addButtonClass}>
            <Plus size={16} /> add milestone
          </button>
          <button type="button" onClick={() => onOpenAddStep(null)} className={addButtonClass}>
            <Plus size={16} /> add step
          </button>
          <button type="button" onClick={onOpenAddResource} className={addButtonClass}>
            <Plus size={16} /> add resource
          </button>
        </div>
      )}

      {milestones.length === 0 && (project.steps || []).length === 0 && (
        <EmptyState className="py-8">
          No plan yet — add a milestone or a step to break this venture down.
        </EmptyState>
      )}

      {/* Milestones with their nested steps. */}
      {milestones.map((ms, idx) => {
        const childSteps = stepsByMilestone.get(ms.id) || [];
        const done = childSteps.filter((s) => s.is_completed).length;
        const total = childSteps.length;
        const collapsed = collapsedMilestones.has(ms.id);
        const allDone = total > 0 && done === total;
        const numeral = chapterMark(idx);
        return (
          <motion.div key={ms.id} layout>
            <ParchmentCard className={ms.is_completed ? 'opacity-60' : ''}>
              <div className="flex items-start gap-3">
                <button
                  type="button"
                  onClick={() => !ms.is_completed && onCompleteMilestone(ms.id)}
                  disabled={ms.is_completed}
                  aria-label={ms.is_completed ? 'Milestone completed' : 'Mark milestone complete'}
                  className={`w-7 h-7 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-all ${
                    ms.is_completed
                      ? 'bg-moss border-moss'
                      : 'border-ink-page-shadow hover:border-sheikah-teal-deep hover:bg-sheikah-teal/15'
                  }`}
                >
                  {ms.is_completed && <Check size={14} className="text-ink-page-rune-glow" strokeWidth={3} />}
                </button>
                <button
                  type="button"
                  onClick={() => toggleMilestone(ms.id)}
                  className="flex-1 min-w-0 text-left"
                >
                  <div className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="font-display italic text-ember-deep text-sm leading-none select-none shrink-0"
                    >
                      {numeral}
                    </span>
                    <div
                      className={`font-display text-base text-ink-primary ${
                        ms.is_completed ? 'line-through' : ''
                      }`}
                    >
                      {ms.title}
                    </div>
                    {ms.bonus_amount && (
                      <span className="font-rune text-xs text-moss flex items-center gap-0.5">
                        <DollarSign size={12} />{ms.bonus_amount}
                      </span>
                    )}
                    <ChevronDown
                      size={14}
                      className={`text-ink-secondary ml-auto transition-transform ${
                        collapsed ? '-rotate-90' : ''
                      }`}
                    />
                  </div>
                  {ms.description && (
                    <div className="font-body text-xs text-ink-secondary mt-0.5">
                      {ms.description}
                    </div>
                  )}
                  {total > 0 && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden flex-1">
                        <div
                          className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                          style={{ width: `${(done / total) * 100}%` }}
                        />
                      </div>
                      <span className="font-rune text-micro text-ink-whisper shrink-0 tabular-nums">
                        {done}/{total}
                      </span>
                    </div>
                  )}
                </button>
                {isParent && (
                  <button
                    type="button"
                    onClick={() => onDeleteMilestone(ms.id)}
                    aria-label="Delete milestone"
                    className="text-ink-secondary hover:text-ember-deep p-1 transition-colors shrink-0"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>

              {!collapsed && (
                <div className="mt-3 ml-10 space-y-2">
                  {allDone && !ms.is_completed && (
                    <button
                      type="button"
                      onClick={() => onCompleteMilestone(ms.id)}
                      className="w-full font-body text-xs bg-sheikah-teal/15 hover:bg-sheikah-teal/25 text-sheikah-teal-deep border border-sheikah-teal/40 rounded-lg py-2 transition-colors"
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
                    <div className="font-script text-xs text-ink-whisper italic">
                      No steps in this milestone yet.
                    </div>
                  )}
                  {isParent && (
                    <button
                      type="button"
                      onClick={() => onOpenAddStep(ms.id)}
                      className={`${addButtonClass} min-w-0 text-xs py-1.5`}
                    >
                      <Plus size={12} /> add step here
                    </button>
                  )}
                </div>
              )}
            </ParchmentCard>
          </motion.div>
        );
      })}

      {looseSteps.length > 0 && (
        <div className="space-y-2">
          {milestones.length > 0 && (
            <div className="font-script text-xs text-ink-whisper uppercase tracking-wider pt-2">
              other steps
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
          <div className="font-script text-xs text-ink-whisper mb-2 uppercase tracking-wider">
            project-level resources
          </div>
          <div className="space-y-1.5">
            {project.resources.map((r) => (
              <ParchmentCard key={r.id} className="flex items-center justify-between py-2">
                <ResourcePill resource={r} />
                <button
                  type="button"
                  onClick={() => onDeleteResource(r.id)}
                  aria-label="Delete resource"
                  className="text-ink-secondary hover:text-ember-deep p-1 transition-colors"
                >
                  <Trash2 size={14} />
                </button>
              </ParchmentCard>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

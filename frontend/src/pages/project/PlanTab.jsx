import { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { Check, ChevronDown, DollarSign, Trash2 } from 'lucide-react';
import EmptyState from '../../components/EmptyState';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { chapterMark } from '../../components/atlas/mastery.constants';
import DashedAddButton from './DashedAddButton';
import { ResourcePill, StepCard } from './ProjectPlanItems';

const LOOSE_KEY = '__loose__';

export default function PlanTab({
  project, isParent,
  pendingMilestoneId,
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
          <DashedAddButton onClick={onOpenAddMilestone}>add milestone</DashedAddButton>
          <DashedAddButton onClick={() => onOpenAddStep(null)}>add step</DashedAddButton>
          <DashedAddButton onClick={onOpenAddResource}>add resource</DashedAddButton>
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
        const isCompleting = pendingMilestoneId === ms.id;
        return (
          <motion.div key={ms.id} layout>
            <ParchmentCard className={ms.is_completed ? 'opacity-60' : ''}>
              <div className="flex items-start gap-3">
                <button
                  type="button"
                  onClick={() => !ms.is_completed && !isCompleting && onCompleteMilestone(ms.id)}
                  disabled={ms.is_completed || isCompleting}
                  aria-busy={isCompleting || undefined}
                  aria-label={ms.is_completed ? 'Milestone completed' : (isCompleting ? 'Marking milestone complete…' : 'Mark milestone complete')}
                  className={`w-7 h-7 rounded-full border-2 flex items-center justify-center shrink-0 mt-0.5 transition-all ${
                    ms.is_completed
                      ? 'bg-moss border-moss'
                      : isCompleting
                        ? 'border-sheikah-teal-deep bg-sheikah-teal/25 animate-pulse cursor-progress'
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
                      className="font-display italic text-ember-deep text-body leading-none select-none shrink-0"
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
                      <span className="font-rune text-caption text-moss flex items-center gap-0.5">
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
                    <div className="font-body text-caption text-ink-secondary mt-0.5">
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
                      onClick={() => !isCompleting && onCompleteMilestone(ms.id)}
                      disabled={isCompleting}
                      aria-busy={isCompleting || undefined}
                      className={`w-full font-body text-caption bg-sheikah-teal/15 hover:bg-sheikah-teal/25 text-sheikah-teal-deep border border-sheikah-teal/40 rounded-lg py-2 transition-colors ${
                        isCompleting ? 'cursor-progress opacity-70' : ''
                      }`}
                    >
                      {isCompleting ? 'Marking complete…' : 'All steps done — mark milestone complete?'}
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
                    <div className="font-script text-caption text-ink-whisper italic">
                      No steps in this milestone yet.
                    </div>
                  )}
                  {isParent && (
                    <DashedAddButton size="sm" onClick={() => onOpenAddStep(ms.id)}>
                      add step here
                    </DashedAddButton>
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
            <div className="font-script text-caption text-ink-whisper uppercase tracking-wider pt-2">
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
          <div className="font-script text-caption text-ink-whisper mb-2 uppercase tracking-wider">
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

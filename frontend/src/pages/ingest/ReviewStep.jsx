import { buttonPrimary } from '../../constants/styles';
import AISuggestions from './AISuggestions';
import ProjectOverridesCard from './ProjectOverridesCard';
import MilestonesEditor from './MilestonesEditor';
import StepsEditor from './StepsEditor';
import ResourcesEditor from './ResourcesEditor';
import MaterialsEditor from './MaterialsEditor';

/**
 * The "preview" phase: AI chips + project overrides + 4 editors + commit row.
 *
 * Mutation handlers are passed in from the shell because some of them are
 * cross-cutting (removing a milestone shifts step.milestone_index; removing
 * a step shifts resource.step_index).
 */
export default function ReviewStep({
  draft, setDraft,
  overrides, setOverrides,
  categories,
  milestoneHandlers, stepHandlers, resourceHandlers, materialHandlers,
  committing, onCommit, onDiscard,
}) {
  return (
    <div className="space-y-4">
      {(draft.warnings?.length > 0 || draft.pipeline_warnings?.length > 0) && (
        <div className="text-xs text-amber-highlight bg-amber-highlight/10 border border-amber-highlight/30 rounded-lg p-3 space-y-1">
          {draft.warnings?.map((w, i) => <div key={`w-${i}`}>⚠ {w}</div>)}
          {draft.pipeline_warnings?.map((w, i) => <div key={`pw-${i}`} className="opacity-70">⚙ {w}</div>)}
        </div>
      )}

      {draft.ai_suggestions && (
        <AISuggestions
          suggestions={draft.ai_suggestions}
          categories={categories}
          overrides={overrides}
          setOverrides={setOverrides}
          setDraft={setDraft}
        />
      )}

      <ProjectOverridesCard
        draft={draft}
        setDraft={setDraft}
        overrides={overrides}
        setOverrides={setOverrides}
        categories={categories}
      />

      <MilestonesEditor
        milestones={draft.milestones}
        onAdd={milestoneHandlers.add}
        onUpdate={milestoneHandlers.update}
        onRemove={milestoneHandlers.remove}
      />

      <StepsEditor
        steps={draft.steps}
        milestones={draft.milestones}
        onAdd={stepHandlers.add}
        onUpdate={stepHandlers.update}
        onRemove={stepHandlers.remove}
      />

      <ResourcesEditor
        resources={draft.resources || []}
        steps={draft.steps}
        onAdd={resourceHandlers.add}
        onUpdate={resourceHandlers.update}
        onRemove={resourceHandlers.remove}
      />

      <MaterialsEditor
        materials={draft.materials}
        onAdd={materialHandlers.add}
        onUpdate={materialHandlers.update}
        onRemove={materialHandlers.remove}
      />

      <div className="flex gap-2">
        <button
          onClick={onCommit}
          disabled={committing}
          className={`flex-1 py-2.5 ${buttonPrimary}`}
        >
          {committing ? 'Creating…' : 'Create Project'}
        </button>
        <button
          onClick={onDiscard}
          className="px-4 py-2.5 rounded-lg border border-forge-border text-sm text-forge-text-dim"
        >
          Discard
        </button>
      </div>
    </div>
  );
}

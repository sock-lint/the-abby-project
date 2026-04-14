import Card from '../../components/Card';
import StarRating from '../../components/StarRating';

const chipClass =
  'text-xs px-2 py-1 rounded-full border border-fuchsia-400/40 text-fuchsia-200 hover:bg-fuchsia-400/10';

/**
 * Renders Claude's enrichment chips. Each chip is opt-in — clicking applies
 * the suggestion to draft / overrides without auto-mutating anything.
 */
export default function AISuggestions({
  suggestions, categories, overrides, setOverrides, setDraft,
}) {
  const applyCategory = () => {
    const match = categories.find(
      (c) => c.name.toLowerCase() === String(suggestions.category).toLowerCase(),
    );
    if (match) setOverrides({ ...overrides, category_id: match.id });
  };

  const applyDifficulty = () =>
    setOverrides({ ...overrides, difficulty: suggestions.difficulty });

  const appendStep = (s) =>
    setDraft((d) => ({
      ...d,
      steps: [
        ...d.steps,
        {
          title: s.title || `Step ${d.steps.length + 1}`,
          description: s.description || '',
          order: d.steps.length,
        },
      ],
    }));

  const appendResource = (r) =>
    setDraft((d) => ({
      ...d,
      resources: [
        ...(d.resources || []),
        {
          title: r.title || '',
          url: r.url || '',
          resource_type: r.resource_type || 'link',
          order: (d.resources || []).length,
          step_index: Number.isInteger(r.step_index) ? r.step_index : null,
        },
      ],
    }));

  return (
    <Card className="border-royal/30 bg-fuchsia-400/5 space-y-2">
      <div className="text-xs font-semibold text-royal uppercase tracking-wide">
        ✨ Claude suggestions
      </div>
      {suggestions.summary && (
        <div className="text-sm text-ink-primary">{suggestions.summary}</div>
      )}
      <div className="flex flex-wrap gap-2">
        {suggestions.category && (
          <button type="button" onClick={applyCategory} className={chipClass}>
            Category: {suggestions.category}
          </button>
        )}
        {suggestions.difficulty && (
          <button type="button" onClick={applyDifficulty} className={chipClass}>
            Difficulty: <StarRating value={suggestions.difficulty} />
          </button>
        )}
        {(suggestions.skill_tags || []).map((tag, i) => (
          <span key={i} className={chipClass.replace(' hover:bg-fuchsia-400/10', '')}>
            {tag}
          </span>
        ))}
      </div>
      {suggestions.extra_materials?.length > 0 && (
        <div className="text-xs text-ink-whisper">
          Suggested extras: {suggestions.extra_materials.map((m) => m.name).join(', ')}
        </div>
      )}
      {suggestions.steps?.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-royal font-medium">Suggested walkthrough steps</div>
          <div className="flex flex-wrap gap-2">
            {suggestions.steps.map((s, i) => (
              <button
                key={`ais-${i}`}
                type="button"
                onClick={() => appendStep(s)}
                className={`${chipClass} text-left`}
              >
                + {s.title?.slice(0, 40) || `Step ${i + 1}`}
              </button>
            ))}
          </div>
        </div>
      )}
      {suggestions.resources?.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs text-royal font-medium">Suggested resources</div>
          <div className="flex flex-wrap gap-2">
            {suggestions.resources.map((r, i) => (
              <button
                key={`air-${i}`}
                type="button"
                onClick={() => appendResource(r)}
                className={chipClass}
              >
                + {r.title?.slice(0, 30) || r.url?.slice(0, 30) || 'link'}
              </button>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

import { useMemo } from 'react';
import { X, Plus } from 'lucide-react';
import { SelectField } from './form';
import Button from './Button';
import IconButton from './IconButton';

/**
 * Parent UI for editing `skill_tags` on chores, habits, and quests.
 *
 * Value shape: `[{ skill_id, xp_weight }]`. Parents add rows (pick a
 * skill, set a weight), remove rows, and the component emits a new
 * array via `onChange`. Skills are grouped by category in the
 * dropdown so parents can navigate by domain.
 *
 * The component is intentionally stateless about order — rows are
 * keyed by `skill_id` so the same skill can't be picked twice (the
 * dropdown filters out already-used skills).
 */
export default function SkillTagEditor({ skills = [], value = [], onChange }) {
  const tags = Array.isArray(value) ? value : [];
  const skillById = useMemo(() => {
    const m = new Map();
    for (const s of skills) m.set(s.id, s);
    return m;
  }, [skills]);

  const grouped = useMemo(() => {
    const used = new Set(tags.map((t) => t.skill_id));
    const byCat = new Map();
    for (const s of skills) {
      if (used.has(s.id)) continue;
      const cat = s.category_name || 'Other';
      if (!byCat.has(cat)) byCat.set(cat, []);
      byCat.get(cat).push(s);
    }
    return [...byCat.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [skills, tags]);

  const unused = grouped.length > 0;
  const totalWeight = tags.reduce((a, t) => a + (Number(t.xp_weight) || 0), 0);

  const updateRow = (idx, patch) => {
    const next = tags.map((t, i) => (i === idx ? { ...t, ...patch } : t));
    onChange(next);
  };

  const removeRow = (idx) => {
    onChange(tags.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    const first = grouped[0]?.[1]?.[0];
    if (!first) return;
    onChange([...tags, { skill_id: first.id, xp_weight: 1 }]);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <label className="font-body text-sm text-ink-primary">
          Skills this rewards
        </label>
        {tags.length > 1 && (
          <span className="font-script text-tiny text-ink-secondary">
            Split by weight · total {totalWeight}
          </span>
        )}
      </div>
      <p className="font-script text-tiny text-ink-whisper -mt-1">
        tags route XP to skills on approval — weights split the pool
      </p>
      {tags.length === 0 && (
        <p className="font-body text-caption text-ink-secondary italic">
          No skills tagged — this awards coins only, nothing in the skill tree.
        </p>
      )}
      <ul className="space-y-2">
        {tags.map((tag, idx) => {
          const skill = skillById.get(tag.skill_id);
          const available = [
            ...grouped.flatMap(([, list]) => list),
            skill, // include the currently-selected row's skill
          ].filter(Boolean);
          const availableByCat = new Map();
          for (const s of available) {
            const cat = s.category_name || 'Other';
            if (!availableByCat.has(cat)) availableByCat.set(cat, []);
            availableByCat.get(cat).push(s);
          }
          return (
            <li key={tag.skill_id || `new-${idx}`} className="flex gap-2 items-start">
              <div className="flex-1">
                <SelectField
                  label=""
                  value={tag.skill_id || ''}
                  onChange={(e) =>
                    updateRow(idx, { skill_id: parseInt(e.target.value, 10) })
                  }
                  aria-label={`Skill for tag ${idx + 1}`}
                >
                  {[...availableByCat.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(
                    ([cat, list]) => (
                      <optgroup key={cat} label={cat}>
                        {list.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.icon ? `${s.icon} ` : ''}{s.name}
                          </option>
                        ))}
                      </optgroup>
                    ),
                  )}
                </SelectField>
              </div>
              <div className="w-24">
                <SelectField
                  label=""
                  value={tag.xp_weight ?? 1}
                  onChange={(e) =>
                    updateRow(idx, { xp_weight: parseInt(e.target.value, 10) })
                  }
                  aria-label={`Weight for tag ${idx + 1}`}
                >
                  {[1, 2, 3, 4, 5].map((w) => (
                    <option key={w} value={w}>{w}</option>
                  ))}
                </SelectField>
              </div>
              <IconButton
                onClick={() => removeRow(idx)}
                aria-label={`Remove ${skill?.name || 'skill tag'}`}
                variant="ghost"
                size="sm"
                className="mt-1"
              >
                <X className="w-4 h-4" />
              </IconButton>
            </li>
          );
        })}
      </ul>
      {unused && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={addRow}
          className="inline-flex items-center gap-1"
        >
          <Plus className="w-4 h-4" />
          Add skill
        </Button>
      )}
    </div>
  );
}

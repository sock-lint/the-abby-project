import Button from '../../components/Button';
import { SelectField, TextField } from '../../components/form';
import { CHALLENGE_GATE_MODES, challengeQuestLabel } from './progressionLabScenario';

const blankRule = (quest_id) => ({ quest_id, prerequisite_quest_id: null, skill_id: null, skill_level: 0, min_days: 0, available_from: null, available_until: null });

export default function ProgressionChallengeGateControls({ gates, metadata, onChange, errors = {}, modeLocked = false, label = 'Challenge gates' }) {
  const quests = metadata.challenge_gate_choices?.quests ?? [];
  const skills = metadata.challenge_gate_choices?.skills ?? [];
  const targets = quests.filter((quest) => !quest.is_repeatable);
  const maxRules = metadata.challenge_gates_limits?.max_rules ?? 20;
  const changeRule = (index, key, value) => onChange({ ...gates, rules: gates.rules.map((rule, position) => position === index ? { ...rule, [key]: value, ...(key === 'skill_id' && value === null ? { skill_level: 0 } : {}), ...(key === 'quest_id' && value === rule.prerequisite_quest_id ? { prerequisite_quest_id: null } : {}) } : rule) });
  const remaining = targets.filter((quest) => !gates.rules.some((rule) => rule.quest_id === quest.id));
  return <section aria-label={label} className="space-y-3 rounded-lg bg-ink-page-aged p-3">
    <h3 className="font-semibold">{label}</h3>
    <p className="text-body text-ink-secondary">Try when one-time challenges become available in this anonymous simulation. Existing badge prerequisites remain in force. These gates do not change live challenges or rewards.</p>
    {!modeLocked && <SelectField label="Challenge gate policy" value={gates.mode} onChange={(event) => onChange({ ...gates, mode: event.target.value })}>{Object.entries(CHALLENGE_GATE_MODES).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</SelectField>}
    <TextField label="Challenge calendar start date" type="date" min="0001-01-01" max="9998-12-31" required value={gates.start_date} onChange={(event) => onChange({ ...gates, start_date: event.target.value })} error={errors['challenge_gates.start_date']} helpText="Simulation day 1 is the child’s first activity on this date. This date maps challenge availability only; purchasing dates are a separate assumption." />
    <p className="text-caption text-ink-secondary">Current rules ignore the saved gate rules below. Milestone gates apply challenge completion, skill and calendar requirements. Milestone plus tenure also applies elapsed days since first activity: 14 days unlocks on day 15. Every configured requirement must be met.</p>
    {gates.rules.map((rule, index) => <fieldset key={index} className="min-w-0 space-y-3 rounded-lg border border-ink-whisper/30 p-3">
      <legend className="font-semibold px-1">Challenge gate {index + 1}</legend>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <SelectField label={`Gate ${index + 1} challenge`} value={rule.quest_id} onChange={(event) => changeRule(index, 'quest_id', Number(event.target.value))}>{targets.filter((quest) => quest.id === rule.quest_id || !gates.rules.some((other) => other.quest_id === quest.id)).map((quest) => <option key={quest.id} value={quest.id}>{challengeQuestLabel(quest, quests)}</option>)}</SelectField>
        <SelectField label={`Gate ${index + 1} previous challenge`} value={rule.prerequisite_quest_id ?? ''} onChange={(event) => changeRule(index, 'prerequisite_quest_id', event.target.value === '' ? null : Number(event.target.value))}><option value="">No previous challenge required</option>{quests.filter((quest) => quest.id !== rule.quest_id).map((quest) => <option key={quest.id} value={quest.id}>{challengeQuestLabel(quest, quests)}{quest.is_repeatable ? ' (first completion)' : ''}</option>)}</SelectField>
        <SelectField label={`Gate ${index + 1} skill`} value={rule.skill_id ?? ''} onChange={(event) => changeRule(index, 'skill_id', event.target.value === '' ? null : Number(event.target.value))}><option value="">No skill requirement</option>{skills.map((skill) => <option key={skill.id} value={skill.id}>{skill.category} / {skill.name}</option>)}</SelectField>
        <TextField label={`Gate ${index + 1} skill level`} type="number" min="0" max="6" step="1" required disabled={rule.skill_id === null} value={rule.skill_level} onChange={(event) => changeRule(index, 'skill_level', event.target.value === '' ? '' : Number(event.target.value))} />
        <TextField label={`Gate ${index + 1} elapsed days since first activity`} type="number" min="0" max="365" step="1" required value={rule.min_days} onChange={(event) => changeRule(index, 'min_days', event.target.value === '' ? '' : Number(event.target.value))} helpText="Applied only by milestone plus tenure. Elapsed calendar days include days without a visit." />
        <TextField label={`Gate ${index + 1} available from`} type="date" min="0001-01-01" max="9999-12-31" value={rule.available_from ?? ''} onChange={(event) => changeRule(index, 'available_from', event.target.value || null)} helpText="Optional first day the challenge can be offered, inclusive." />
        <TextField label={`Gate ${index + 1} available until`} type="date" min="0001-01-01" max="9999-12-31" value={rule.available_until ?? ''} onChange={(event) => changeRule(index, 'available_until', event.target.value || null)} helpText="Optional last day it can be offered, inclusive. An accepted challenge keeps its full native completion window." />
      </div>
      <Button variant="ghost" onClick={() => onChange({ ...gates, rules: gates.rules.filter((_, position) => position !== index) })}>Remove challenge gate {index + 1}</Button>
    </fieldset>)}
    <Button variant="secondary" disabled={!remaining.length || gates.rules.length >= maxRules} onClick={() => onChange({ ...gates, rules: [...gates.rules, blankRule(remaining[0].id)] })}>Add challenge gate</Button>
    {!targets.length && <p className="text-caption text-ink-secondary">No compatible one-time catalog challenge choices are available.</p>}
    <p className="text-caption text-ink-secondary">Up to {maxRules} challenge rules. Gating can postpone or remove access; it does not add content. The report separates available challenges, gate waiting and expired windows.</p>
    {errors.challenge_gates && <p role="alert">{errors.challenge_gates}</p>}
  </section>;
}

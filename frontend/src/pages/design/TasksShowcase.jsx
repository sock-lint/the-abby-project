import { useState } from 'react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RuneBadge from '../../components/journal/RuneBadge';
import { SelectField } from '../../components/form';
import ChallengesFolio from '../trials/ChallengesFolio';
import { ChallengeGoalDetail } from '../trials/ChallengeGoalCard';
import { TASKS_SHOWCASE_GOALS, TASKS_SHOWCASE_PIN, TASKS_SHOWCASE_TIMEZONE } from './tasks.fixtures';

function SampleDailyBonus() {
  return (
    <ParchmentCard as="section" aria-label="Sample daily bonus" className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-body text-body font-bold text-ink-primary">Today’s bonus</h3>
        <RuneBadge tone="moss">Earned</RuneBadge>
      </div>
      <p className="font-body text-body text-ink-secondary">10 coins · 20 XP earned automatically</p>
      <p className="font-body text-caption text-ink-secondary">One daily bonus for qualifying work, alongside challenge progress.</p>
    </ParchmentCard>
  );
}

export default function TasksShowcase() {
  const [pinId, setPinId] = useState(TASKS_SHOWCASE_PIN);
  const [selectedId, setSelectedId] = useState(null);
  const [role, setRole] = useState('child');
  const isParent = role === 'parent';
  const goals = TASKS_SHOWCASE_GOALS.map((goal) => ({ ...goal, pinned: goal.id === pinId }));
  const pinnedGoal = goals.find((goal) => goal.pinned) || null;
  const selectedGoal = goals.find((goal) => goal.id === selectedId);
  const onPin = isParent ? undefined : (goal) => setPinId((current) => current === goal.id ? null : goal.id);

  return (
    <section id="task-folio" aria-labelledby="task-folio-title" className="space-y-4 scroll-mt-4">
      <header className="space-y-2">
        <h2 id="task-folio-title" className="font-display text-2xl font-bold text-ink-primary">Task folio</h2>
        <p className="font-body text-body text-ink-secondary max-w-prose">
          The shared Tasks layout pairs a compact summary with a focused working list.
          These synthetic challenge examples use the same components as Tasks → Challenges.
          Pins and details change only this local preview.
        </p>
        <div className="max-w-xs">
          <SelectField label="Preview role" value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="child">Child</option>
            <option value="parent">Parent</option>
          </SelectField>
        </div>
      </header>
      <ChallengesFolio
        goals={goals}
        pinnedGoal={pinnedGoal}
        timezone={TASKS_SHOWCASE_TIMEZONE}
        isParent={isParent}
        onSelect={(goal) => setSelectedId(goal.id)}
        onPin={onPin}
        dailyBonus={!isParent && <SampleDailyBonus />}
      />
      {selectedGoal && <ChallengeGoalDetail
        goal={selectedGoal}
        timezone={TASKS_SHOWCASE_TIMEZONE}
        onClose={() => setSelectedId(null)}
        onPin={onPin}
        canAct={false}
      />}
    </section>
  );
}

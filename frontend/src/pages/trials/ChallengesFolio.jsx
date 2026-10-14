import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import QuestFolio from '../quests/QuestFolio';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import EmptyState from '../../components/EmptyState';
import ChallengeGoalCard from './ChallengeGoalCard';
import { challengeFocus } from './challengeFocus';
import { goalProgress } from './goalDisplay';

function GoalDisclosure({ title, children }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/40 p-4" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary data-challenge-disclosure={title === 'Browse bonus challenges' ? 'bonus' : 'history'} className="font-body font-bold text-body text-ink-primary cursor-pointer min-h-11 flex items-center gap-2">
        {title}
        <ChevronDown size={16} aria-hidden="true" className={`ml-auto shrink-0 transition-transform motion-reduce:transition-none ${open ? 'rotate-180' : ''}`} />
      </summary>
      {open && <div className="mt-3 space-y-3">{children}</div>}
    </details>
  );
}

export default function ChallengesFolio({ goals = [], pinnedGoal = null, timezone = 'UTC', isParent = false, onSelect, onPin, busy = false, toolbar = null, dailyBonus = null }) {
  const focus = challengeFocus(goals, pinnedGoal);
  const cardProps = { timezone, onSelect, onPin, busy, isParent };
  const cards = (rows, showDeadline = true) => (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      {rows.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} {...cardProps} showDeadline={showDeadline} />)}
    </div>
  );
  let sectionIndex = 0;
  return (
    <QuestFolio
      letter="C" title="Challenges" kicker="Focus on the goals that matter to you"
      meta="Your usual tasks can earn extra rewards."
      stats={[{ value: focus.parentCount, label: 'parent goals' }, { value: focus.pinned ? 1 : 0, label: 'pinned' }]}
      progressPct={focus.pinnedProgress}
      progressLabel={focus.pinned ? `${focus.pinned.name} · ${goalProgress(focus.pinned)}` : undefined}
    >
      <p className="font-body text-body text-ink-secondary">All matching challenges keep progressing in the background. Pinning simply keeps one on Today.</p>
      {toolbar}
      {focus.pinned && <section className="space-y-3" aria-label="Pinned challenge">
        <ChapterRubric index={sectionIndex++} name="Pinned to Today" />
        <ChallengeGoalCard goal={focus.pinned} {...cardProps} />
      </section>}
      {focus.parentGoals.length > 0 && <section className="space-y-3" aria-label="Parent goals">
        <ChapterRubric index={sectionIndex++} name="Parent goals" />
        {cards(focus.parentGoals)}
      </section>}
      {focus.upcoming.length > 0 && <section className="space-y-3" aria-label="Upcoming challenges">
        <ChapterRubric index={sectionIndex++} name="Upcoming goals" />
        {cards(focus.upcoming)}
      </section>}
      {!focus.pinned && !focus.parentGoals.length && !focus.upcoming.length && <EmptyState>
        {isParent ? 'Create a goal for this child, or explore their bonus challenges below.' : 'Parent goals and any challenge you pin will appear here. Your usual activity already counts toward matching bonuses.'}
      </EmptyState>}
      {dailyBonus}
      {focus.bonusPreview.length > 0 && <section className="space-y-3" aria-label="Bonus progress">
        <ChapterRubric index={sectionIndex++} name="Bonus progress" />
        <p className="font-body text-caption text-ink-secondary">A few bonus challenges your activity is moving toward completion.</p>
        {cards(focus.bonusPreview, false)}
      </section>}
      {focus.otherBonuses.length > 0 && <GoalDisclosure title="Browse bonus challenges">
        <p className="font-body text-caption text-ink-secondary">These optional bonuses track automatically too. Open a challenge for its activity rules and bonus period.</p>
        {cards(focus.otherBonuses, false)}
      </GoalDisclosure>}
      <GoalDisclosure title={`History · ${focus.history.length}`}>
        {focus.history.length ? cards(focus.history) : <p className="font-body text-body text-ink-secondary">No completed or ended challenges yet.</p>}
      </GoalDisclosure>
    </QuestFolio>
  );
}

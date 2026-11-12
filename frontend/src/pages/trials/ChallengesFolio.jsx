import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import QuestFolio from '../quests/QuestFolio';
import ChapterRubric from '../../components/atlas/ChapterRubric';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/Button';
import ChallengeGoalCard from './ChallengeGoalCard';
import { challengeFocus } from './challengeFocus';
import { goalProgress } from './goalDisplay';
import BonusChallengeBrowser from './BonusChallengeBrowser';
import { SelectField } from '../../components/form';
import LockedCatalogChallenges from './LockedCatalogChallenges';

function GoalDisclosure({ title, children, onOpenChange, controlledOpen }) {
  const [open, setOpen] = useState(false);
  const expanded = controlledOpen ?? open;
  return (
    <details open={controlledOpen} className="rounded-xl border border-ink-page-shadow bg-ink-page-aged/40 p-4" onToggle={(event) => { setOpen(event.currentTarget.open); onOpenChange?.(event.currentTarget.open); }}>
      <summary data-challenge-disclosure={title === 'Browse bonus challenges' ? 'bonus' : 'history'} className="font-body font-bold text-body text-ink-primary cursor-pointer min-h-11 flex items-center gap-2">
        {title}
        <ChevronDown size={16} aria-hidden="true" className={`ml-auto shrink-0 transition-transform motion-reduce:transition-none ${expanded ? 'rotate-180' : ''}`} />
      </summary>
      {expanded && <div className="mt-3 space-y-3">{children}</div>}
    </details>
  );
}

export default function ChallengesFolio({ goals = [], lockedCatalog = [], pinnedGoal = null, timezone = 'UTC', isParent = false, isPersonalParent = false, onSelect, onPin, onRetry, busy = false, toolbar = null, dailyBonus = null }) {
  const [browsing, setBrowsing] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyFilter, setHistoryFilter] = useState('all');
  const focus = challengeFocus(goals, pinnedGoal);
  const bonusGoals = goals.filter((goal) => goal.status === 'active' && goal.origin !== 'parent' && goal.id !== focus.pinned?.id);
  const retryable = focus.history.filter((goal) => goal.retry?.allowed === true);
  const historyRows = historyFilter === 'retryable' ? retryable : focus.history;
  const cardProps = { timezone, onSelect, onPin, onRetry, busy, isParent, isPersonalParent };
  const cards = (rows) => (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
      {rows.map((goal) => <ChallengeGoalCard key={goal.id} goal={goal} {...cardProps} />)}
    </div>
  );
  let sectionIndex = 0;
  return (
    <QuestFolio
      letter="C" title="Challenges" kicker="Focus on the goals that matter to you"
      meta="Your usual tasks can earn extra rewards."
      stats={[{ value: focus.parentCount, label: isPersonalParent ? 'personal goals' : 'parent goals' }, { value: focus.pinned ? 1 : 0, label: 'pinned' }]}
      progressPct={focus.pinnedProgress}
      progressLabel={focus.pinned ? `${focus.pinned.name} · ${goalProgress(focus.pinned)}` : undefined}
    >
      <p className="font-body text-body text-ink-secondary">All matching challenges keep progressing in the background. Pinning simply keeps one on Today.</p>
      {toolbar}
      {focus.pinned && <section className="space-y-3" aria-label="Pinned challenge">
        <ChapterRubric index={sectionIndex++} name="Pinned to Today" />
        <ChallengeGoalCard goal={focus.pinned} {...cardProps} />
      </section>}
      {focus.parentGoals.length > 0 && <section className="space-y-3" aria-label={isPersonalParent ? 'Personal goals' : 'Parent goals'}>
        <ChapterRubric index={sectionIndex++} name={isPersonalParent ? 'Personal goals' : 'Parent goals'} />
        {cards(focus.parentGoals)}
      </section>}
      {focus.upcoming.length > 0 && <section className="space-y-3" aria-label="Upcoming challenges">
        <ChapterRubric index={sectionIndex++} name="Upcoming goals" />
        {cards(focus.upcoming)}
      </section>}
      {!focus.pinned && !focus.parentGoals.length && !focus.upcoming.length && <EmptyState>
        {isParent ? 'Create a goal for this child, or explore their bonus challenges below.' : isPersonalParent ? 'Create a personal goal or pin a challenge. Your usual activity already counts toward matching bonuses.' : 'Parent goals and any challenge you pin will appear here. Your usual activity already counts toward matching bonuses.'}
      </EmptyState>}
      {dailyBonus}
      {!browsing && focus.explore.length > 0 && <section className="space-y-3" aria-label="Explore challenges">
        <ChapterRubric index={sectionIndex++} name="Explore challenges" />
        <p className="font-body text-caption text-ink-secondary">Open an available challenge to see its details. Your usual activity already counts.</p>
        {cards(focus.explore)}
      </section>}
      {!browsing && focus.bonusPreview.length > 0 && <section className="space-y-3" aria-label="Bonus progress">
        <ChapterRubric index={sectionIndex++} name="Bonus progress" />
        <p className="font-body text-caption text-ink-secondary">A few bonus challenges your activity is moving toward completion.</p>
        {cards(focus.bonusPreview)}
      </section>}
      {bonusGoals.length > 0 && <GoalDisclosure title="Browse bonus challenges" onOpenChange={setBrowsing}>
        <BonusChallengeBrowser goals={bonusGoals} renderCards={cards} timezone={timezone} />
      </GoalDisclosure>}
      <LockedCatalogChallenges definitions={lockedCatalog} sectionIndex={sectionIndex++} />
      {retryable.length > 0 && <div className="space-y-2"><p className="font-body text-caption text-ink-secondary">{retryable.length} ended {retryable.length === 1 ? 'challenge can' : 'challenges can'} be tried again with a fresh period. Each challenge&apos;s bonus can be earned once.</p><Button variant="secondary" onClick={() => { setHistoryFilter('retryable'); setHistoryOpen(true); }}>Find challenges to try again</Button></div>}
      <GoalDisclosure title={`History · ${focus.history.length}`} controlledOpen={historyOpen} onOpenChange={setHistoryOpen}>
        {(retryable.length > 0 || historyFilter !== 'all') && <SelectField label="Show history" value={historyFilter} onChange={(event) => setHistoryFilter(event.target.value)}><option value="all">All completed and ended challenges</option><option value="retryable">Can try again</option></SelectField>}
        {historyRows.length ? cards(historyRows) : <p className="font-body text-body text-ink-secondary">{historyFilter === 'retryable' ? 'No challenges can be tried again right now.' : 'No completed or ended challenges yet.'}</p>}
      </GoalDisclosure>
    </QuestFolio>
  );
}

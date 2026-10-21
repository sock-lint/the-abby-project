import { useState } from 'react';
import CatalogSearch from '../../components/CatalogSearch';
import EmptyState from '../../components/EmptyState';
import Button from '../../components/Button';
import { SelectField, TextField } from '../../components/form';
import { goalFinalDate, goalTargetSummary } from './goalDisplay';

const ACTIVITY_LABELS = {
  chore_complete: 'Approved chores', homework_complete: 'Approved homework', homework_created: 'Planned homework',
  habit_log: 'Positive habit taps', clock_out: 'Project work', milestone_complete: 'Project milestones',
  project_complete: 'Completed projects', movement_session: 'Movement', reading_logged: 'Daily Reading Adventures',
  journal_entry: 'Journal entries', creation_logged: 'Logged creations', savings_goal_complete: 'Savings goals',
  expedition_returned: 'Expedition returns', badge_earned: 'Earned badges', perfect_day: 'Perfect days',
};
const triggers = (goal) => Array.isArray(goal.qualifying_triggers) ? goal.qualifying_triggers : [];
const unknown = (goal) => !triggers(goal).length || triggers(goal).some((trigger) => !ACTIVITY_LABELS[trigger]);
const ratio = (goal) => Number(goal.target) > 0 ? Number(goal.progress) / Number(goal.target) || 0 : 0;

export default function BonusChallengeBrowser({ goals, renderCards, timezone = 'UTC' }) {
  const [query, setQuery] = useState('');
  const [activity, setActivity] = useState('all');
  const [deadline, setDeadline] = useState('');
  const [order, setOrder] = useState('deadline');
  const available = Object.entries(ACTIVITY_LABELS).filter(([key]) => goals.some((goal) => triggers(goal).includes(key)));
  const filtered = Boolean(query || activity !== 'all' || deadline || order !== 'deadline');
  const clear = () => { setQuery(''); setActivity('all'); setDeadline(''); setOrder('deadline'); };
  const rows = goals.filter((goal) => (
    (!query.trim() || `${goal.name} ${goal.description || ''} ${goalTargetSummary(goal)}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
    && (activity === 'all' || (activity === 'unknown' ? unknown(goal) : triggers(goal).includes(activity)))
    && (!deadline || (goalFinalDate(goal, timezone) && goalFinalDate(goal, timezone) <= deadline))
  )).sort((left, right) => (
    (order === 'progress' ? ratio(right) - ratio(left) : order === 'deadline'
      ? (Date.parse(left.ends_at) || Infinity) - (Date.parse(right.ends_at) || Infinity) : 0)
    || left.name.localeCompare(right.name) || left.id.localeCompare(right.id)
  ));
  return <section aria-label="Browse all bonus challenges" className="space-y-3">
    <p className="font-body text-caption text-ink-secondary">Browse every available bonus beyond your pinned focus. Matching work counts while these filters are active.</p>
    <CatalogSearch ariaLabel="Search bonus challenges" placeholder="Search names and qualifying activity…" value={query} onChange={setQuery} />
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
      <SelectField label="Qualifying activity" value={activity} onChange={(event) => setActivity(event.target.value)}>
        <option value="all">All activities</option>
        {available.map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        {goals.some(unknown) && <option value="unknown">Other or unspecified activity</option>}
      </SelectField>
      <TextField label="Ends on or before" type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} helpText="Final included date in each challenge's saved timezone." />
      <SelectField label="Sort bonus challenges" value={order} onChange={(event) => setOrder(event.target.value)}>
        <option value="deadline">Soonest deadline</option><option value="progress">Most progress</option><option value="name">Name</option>
      </SelectField>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <p role="status" className="font-body text-caption text-ink-secondary">{rows.length} of {goals.length} bonus {goals.length === 1 ? 'challenge' : 'challenges'}</p>
      {filtered && <Button variant="ghost" size="sm" onClick={clear}>Clear filters</Button>}
    </div>
    {deadline && <p className="font-body text-caption text-ink-secondary">Challenges without a known deadline are excluded by this date filter.</p>}
    {rows.length ? renderCards(rows) : <EmptyState>No bonus challenges match these filters.</EmptyState>}
  </section>;
}

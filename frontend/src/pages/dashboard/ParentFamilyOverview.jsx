import { Link } from 'react-router-dom';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ProgressBar from '../../components/ProgressBar';
import { formatCurrency, formatDate } from '../../utils/format';

const ACCOMPLISHMENT_LABELS = {
  badge: 'Earned a badge', homework: 'Homework approved',
  chore: 'Chore approved', goal: 'Goal completed',
};

const linkClass = 'inline-flex min-h-11 items-center text-sheikah-teal-deep font-body font-semibold text-caption hover:underline';

function GoalPreview({ goal }) {
  const progress = Number(goal.progress);
  const target = Number(goal.target);
  return (
    <li className="space-y-1">
      <p className="font-body text-body text-ink-primary break-words">{goal.name}</p>
      <p className="font-body text-caption text-ink-secondary">
        {progress.toLocaleString()} / {target.toLocaleString()} {goal.unit}
      </p>
      <ProgressBar value={progress} max={target} aria-label={`${goal.name} progress`} />
    </li>
  );
}

export default function ParentFamilyOverview({ overview, children, weekByKid, loading, unavailable }) {
  const hasOverview = Boolean(overview && Array.isArray(overview.children) && !unavailable);
  const rows = hasOverview ? overview.children : children.map((child) => ({
    kid_id: child.id,
    name: child.display_name || child.username,
    clocked_week: weekByKid.find((week) => week.kid_id === child.id),
  }));
  return (
    <div className="space-y-3">
      {hasOverview && (
        <p className="font-body text-caption text-ink-secondary">
          {formatDate(overview.date)} · household day ({overview.timezone})
        </p>
      )}
      {hasOverview && loading && (
        <p role="status" className="font-body text-caption text-ink-secondary">Updating family overview…</p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
        {rows.map((child) => {
          const { homework, chores, parent_goals: goals, recent_accomplishment: accomplishment } = child;
          const week = child.clocked_week;
          return (
            <ParchmentCard key={child.kid_id} as="article" className="h-full space-y-3 min-w-0">
              <h3 className="font-display text-lede text-ink-primary break-words">{child.name}</h3>
              {hasOverview ? (
                <>
                  <div>
                    <p className="font-body font-semibold text-body text-ink-primary">Homework</p>
                    <p className="font-body text-caption text-ink-secondary">
                      {homework.due_today} due today · {homework.overdue} overdue
                    </p>
                    {homework.pending_review > 0 && (
                      <p className="font-body text-caption text-ink-secondary">{homework.pending_review} awaiting your review</p>
                    )}
                    <Link className={linkClass} to={`/quests?tab=study&child=${child.kid_id}`} aria-label={`View ${child.name}'s homework`}>
                      View homework
                    </Link>
                  </div>
                  <div>
                    <p className="font-body font-semibold text-body text-ink-primary">Chores</p>
                    <p className="font-body text-caption text-ink-secondary">
                      {chores.remaining} remaining · {chores.pending_review} awaiting review · {chores.approved} approved
                    </p>
                    <Link className={linkClass} to={`/quests?tab=duties&child=${child.kid_id}`} aria-label={`View ${child.name}'s chores`}>
                      View chores
                    </Link>
                  </div>
                  <div className="space-y-2">
                    <p className="font-body font-semibold text-body text-ink-primary">Parent goals</p>
                    {goals.items.length > 0 ? (
                      <ul className="space-y-3">{goals.items.map((goal) => <GoalPreview key={goal.id} goal={goal} />)}</ul>
                    ) : (
                      <p className="font-body text-caption text-ink-secondary">No active parent goals.</p>
                    )}
                    <Link className={linkClass} to={`/quests?tab=trials&child=${child.kid_id}`} aria-label={`View ${child.name}'s goals`}>
                      {goals.active_count > goals.items.length ? `View all ${goals.active_count} goals` : 'View goals'}
                    </Link>
                  </div>
                  <div className="rounded-xl bg-moss/10 p-3">
                    <p className="font-body font-semibold text-caption text-ink-primary">Recent accomplishment</p>
                    <p className="font-body text-caption text-ink-secondary break-words">
                      {accomplishment
                        ? `${ACCOMPLISHMENT_LABELS[accomplishment.kind] || 'Completed'}: ${accomplishment.title}`
                        : 'New accomplishments will appear here.'}
                    </p>
                  </div>
                </>
              ) : (
                <p className="font-body text-caption text-ink-secondary">
                  {loading ? 'Updating daily summary…' : 'Daily summary unavailable.'}
                </p>
              )}
              <div className="pt-2 border-t border-ink-page-shadow">
                <p className="font-body text-caption text-ink-secondary">
                  {unavailable ? 'Weekly activity unavailable.'
                    : loading ? 'Updating weekly activity…'
                      : week ? `${week.hours ?? 0}h clocked · ${formatCurrency(week.earnings)} clocked earnings`
                        : 'No clocked time this week.'}
                </p>
                <Link className={linkClass} to={`/chronicle?tab=yearbook&child=${child.kid_id}`} aria-label={`View ${child.name}'s timeline`}>
                  View timeline
                </Link>
              </div>
            </ParchmentCard>
          );
        })}
      </div>
    </div>
  );
}

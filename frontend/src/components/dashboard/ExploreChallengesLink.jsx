import { Link } from 'react-router-dom';
import { challengeFocus } from '../../pages/trials/challengeFocus';

export default function ExploreChallengesLink({ goals = [], pinnedGoal = null }) {
  const count = challengeFocus(goals, pinnedGoal).explore.length;
  if (!count) return null;
  return <Link to="/quests?tab=trials" className="min-h-11 rounded-lg border border-ink-page-shadow p-3 flex flex-wrap items-center justify-between gap-2 font-body text-body text-sheikah-teal-deep focus-visible:outline-2 focus-visible:outline-offset-2">
    <span className="font-bold">Explore challenges</span>
    <span className="text-caption text-ink-secondary">{count} {count === 1 ? 'challenge' : 'challenges'} to explore</span>
  </Link>;
}

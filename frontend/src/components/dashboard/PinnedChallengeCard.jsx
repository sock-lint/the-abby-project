import { useNavigate } from 'react-router-dom';
import ParchmentCard from '../journal/ParchmentCard';
import Button from '../Button';
import ProgressBar from '../ProgressBar';
import { goalActionPath, goalProgress } from '../../pages/trials/goalDisplay';

export default function PinnedChallengeCard({ goal }) {
  const navigate = useNavigate();
  if (!goal) return <div className="font-body text-body text-ink-secondary"><Button variant="ghost" onClick={() => navigate('/quests?tab=trials')}>Choose a challenge to pin</Button></div>;
  const path = goalActionPath(goal.action);
  return <ParchmentCard className="space-y-2">
    <p className="font-body text-caption text-sheikah-teal-deep">Pinned challenge</p>
    <h2 className="font-body font-bold text-lede text-ink-primary">{goal.name}</h2>
    <p className="font-body text-body text-ink-secondary">{goalProgress(goal)}</p>
    <ProgressBar value={Number(goal.progress)} max={Number(goal.target)} aria-label={`${goal.name} progress`} />
    <div className="flex flex-wrap gap-2">
      {path && <Button size="sm" onClick={() => navigate(path)}>{goal.action.label}</Button>}
      <Button variant="ghost" size="sm" onClick={() => navigate(`/quests?tab=trials&goal=${encodeURIComponent(goal.id)}`)}>View challenge</Button>
    </div>
  </ParchmentCard>;
}

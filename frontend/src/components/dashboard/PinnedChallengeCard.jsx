import { useNavigate } from 'react-router-dom';
import ParchmentCard from '../journal/ParchmentCard';
import Button from '../Button';
import ProgressBar from '../ProgressBar';
import CatalogIcon from '../rpg/CatalogIcon';
import StorybookFeature from '../../pedestal/StorybookFeature';
import { goalActionPath, goalProgress } from '../../pages/trials/goalDisplay';

export default function PinnedChallengeCard({ goal }) {
  const navigate = useNavigate();
  if (!goal) return <div className="font-body text-body text-ink-secondary"><Button variant="ghost" onClick={() => navigate('/quests?tab=trials')}>Choose a challenge to pin</Button></div>;
  const path = goalActionPath(goal.action);
  return <ParchmentCard>
    <StorybookFeature assetId="card-front-light">
      <div className="space-y-2">
        <p className="font-body text-caption text-sheikah-teal-deep">Pinned challenge</p>
        <div className="flex items-center gap-3">
          {goal.catalog_icon && <CatalogIcon assetId={goal.catalog_icon} size={40} alt={goal.name} className="shrink-0" />}
          <h2 className="min-w-0 break-words font-body font-bold text-lede text-ink-primary">{goal.name}</h2>
        </div>
        <p className="font-body text-body text-ink-secondary">{goalProgress(goal)}</p>
        <ProgressBar value={Number(goal.progress)} max={Number(goal.target)} aria-label={`${goal.name} progress`} />
        <div className="flex flex-wrap gap-2">
          {path && <Button size="sm" onClick={() => navigate(path)}>{goal.action.label}</Button>}
          <Button variant="ghost" size="sm" onClick={() => navigate(`/quests?tab=trials&goal=${encodeURIComponent(goal.id)}`)}>View challenge</Button>
        </div>
      </div>
    </StorybookFeature>
  </ParchmentCard>;
}

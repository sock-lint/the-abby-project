import { useNavigate } from 'react-router-dom';
import useChallenges from '../../hooks/useChallenges';
import { goalProgress } from '../../pages/trials/goalDisplay';

export default function HeaderProgressBand() {
  const navigate = useNavigate();
  const { pinnedGoal } = useChallenges();
  if (!pinnedGoal) return <div aria-hidden="true" className="w-full" style={{ height: 1 }} />;
  const percent = Math.min(100, Math.max(0, Number(pinnedGoal.progress) / Number(pinnedGoal.target) * 100));
  return (
    <div className="pb-3 pl-[max(1rem,env(safe-area-inset-left))] pr-[max(1rem,env(safe-area-inset-right))] lg:px-6">
      <button type="button" onClick={() => navigate(`/quests?tab=trials&goal=${encodeURIComponent(pinnedGoal.id)}`)} aria-label={`Pinned challenge: ${pinnedGoal.name} · ${goalProgress(pinnedGoal)}`} className="block w-full min-h-11 rounded-2xl border border-sheikah-teal/15 bg-ink-page-aged/80 px-3 py-2 text-left hover:bg-sheikah-teal/10">
        <div className="h-1.5 rounded-full bg-sheikah-teal/10 overflow-hidden" aria-hidden="true"><div className="h-full bg-sheikah-teal-deep" style={{ width: `${percent}%` }} /></div>
        <span className="flex flex-wrap justify-between gap-2 pt-1 font-body font-semibold text-caption text-ink-primary"><span>{pinnedGoal.name}</span><span>{goalProgress(pinnedGoal)}</span></span>
      </button>
    </div>
  );
}

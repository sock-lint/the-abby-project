import { useNavigate } from 'react-router-dom';
import { DragonIcon } from '../../components/icons/JournalIcons';
import ParchmentCard from '../../components/journal/ParchmentCard';
import { getActiveQuest } from '../../api';
import { useApi } from '../../hooks/useApi';

/**
 * AdventuresEntry — entry-point card on /sigil that surfaces the Trials
 * (boss / collection quests). Shows the active trial's progress when one
 * exists, otherwise an invitation to visit Trials. Sits on /sigil because
 * Trials is part of the RPG adventure layer alongside Pets + Inventory,
 * not a regular-cadence chore.
 */
export default function AdventuresEntry() {
  const navigate = useNavigate();
  const { data: activeQuest } = useApi(getActiveQuest);
  const isActive = activeQuest && activeQuest.status === 'active';

  return (
    <ParchmentCard variant="sealed" tone="default" flourish>
      <button
        type="button"
        onClick={() => navigate('/trials')}
        className="w-full text-left flex items-start gap-3 p-1 focus:outline-none"
        aria-label={
          isActive
            ? `Adventures — continue ${activeQuest.definition?.name || 'trial'}`
            : 'Adventures — open the Trials page'
        }
      >
        <span className="text-sheikah-teal-deep mt-1 shrink-0" aria-hidden="true">
          <DragonIcon size={24} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="font-script text-xs text-royal uppercase tracking-wider">
            Adventures
          </div>
          <h2 className="font-display italic text-lg text-ink-primary leading-tight mt-0.5">
            {isActive ? activeQuest.definition?.name || 'Active trial' : 'The Trials'}
          </h2>
          {isActive ? (
            <>
              <div className="font-body text-caption text-ink-secondary mt-1">
                {activeQuest.current_progress}/{activeQuest.effective_target} · {activeQuest.progress_percent}%
              </div>
              <div className="h-1.5 mt-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                  style={{
                    width: `${Math.max(0, Math.min(100, Number(activeQuest.progress_percent) || 0))}%`,
                  }}
                />
              </div>
            </>
          ) : (
            <p className="font-body text-caption text-ink-secondary mt-1">
              Boss and collection quests live here — spend a scroll to begin.
            </p>
          )}
          <div className="font-script text-sm text-sheikah-teal-deep mt-2">
            {isActive ? 'Continue →' : 'Enter the Trials →'}
          </div>
        </div>
      </button>
    </ParchmentCard>
  );
}

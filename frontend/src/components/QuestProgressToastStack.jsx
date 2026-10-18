import { useEffect } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Sword } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useQuestProgressToasts } from '../hooks/useQuestProgressToasts';
import NotificationToast from './NotificationToast';
import { TOAST_DURATION_STANDARD } from '../constants/timing';
import { goalProgress } from '../pages/trials/goalDisplay';
import EarnedPetItemActions from './rpg/EarnedPetItemActions';

const MAX_VISIBLE_GOALS = 3;

function Toast({ toast, onDismiss }) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), TOAST_DURATION_STANDARD);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);
  const goals = toast.goals || [];
  const visibleGoals = [...goals]
    .sort((first, second) => Number(Boolean(second.completed)) - Number(Boolean(first.completed)))
    .slice(0, MAX_VISIBLE_GOALS);
  const remaining = goals.length - visibleGoals.length;
  // These activity receipts contain actual awards. Include items from goals
  // outside the bounded summary without interpreting ordinary progress as paid.
  const earnedItems = goals.flatMap((goal) => goal.completed === true && Array.isArray(goal.rewards?.items)
    ? goal.rewards.items : []);

  return (
    <NotificationToast
      tone="info"
      onDismiss={() => onDismiss(toast.id)}
    >
      <Sword size={18} className="text-current shrink-0" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <div className="text-caption font-semibold text-current">
          Challenge progress
        </div>
        {visibleGoals.length > 0 && <ul aria-label="Updated challenges" className="text-caption text-current mt-1 space-y-1">
          {visibleGoals.map((goal) => <li key={goal.id}>
            <span className="block truncate" title={goal.name}>{goal.name}</span>
            <span>{goal.completed ? 'Completed' : goalProgress(goal)}
              {goal.completed && goal.rewards && <> · +{goal.rewards.coins} coins · +{goal.rewards.xp} XP</>}
            </span>
          </li>)}
        </ul>}
        <EarnedPetItemActions items={earnedItems} onNavigate={() => onDismiss(toast.id)} />
        {toast.daily_bonus?.awarded && <div className="text-caption text-current mt-1">Today&apos;s bonus · +{toast.daily_bonus.coins_awarded} coins · +{toast.daily_bonus.xp_awarded} XP</div>}
        {remaining > 0 && <div className="text-caption text-current mt-1">
          <div>+{remaining} more {remaining === 1 ? 'challenge' : 'challenges'}</div>
          <Link to="/quests?tab=trials" onClick={() => onDismiss(toast.id)} className="inline-flex min-h-11 items-center font-semibold underline underline-offset-2">
            View challenges
          </Link>
        </div>}
      </div>
    </NotificationToast>
  );
}

/**
 * Child-only summaries of saved activity receipts. The bounded, keyboard-
 * scrollable tray keeps large batches usable without covering the page.
 */
export default function QuestProgressToastStack({ inline = false }) {
  const { toasts, dismiss } = useQuestProgressToasts();

  const items = (
    <div
      role={toasts.length ? 'region' : undefined}
      aria-label={toasts.length ? 'Challenge updates' : undefined}
      tabIndex={toasts.length ? 0 : undefined}
      className="max-h-[min(50dvh,24rem)] overflow-x-hidden overflow-y-auto overscroll-contain space-y-2 pointer-events-auto empty:hidden"
    >
      <AnimatePresence>
        {toasts.map((t) => (
          <div key={t.id}>
            <Toast toast={t} onDismiss={dismiss} />
          </div>
        ))}
      </AnimatePresence>
    </div>
  );

  if (inline) return items;
  return (
    <div className="fixed top-52 right-4 z-50 space-y-2 w-80 max-w-[calc(100vw-2rem)] pointer-events-none" aria-live="polite" aria-atomic="false">
      {items}
    </div>
  );
}

import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Play, Square, Flame, Sparkles, ClipboardCheck, BookOpen } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
import { formatDuration } from '../../utils/format';
import { inkBleed } from '../../motion/variants';
import { buttonPrimary } from '../../constants/styles';

const ICON_MAP = { BookOpen, Sparkles, Flame, Play, Square, ClipboardCheck };

const TONE_TO_ACCENT_CLASS = {
  royal: 'text-royal',
  moss: 'text-moss',
  ember: 'text-ember-deep',
};

/**
 * HeroPrimaryCard — the single-fold primary card on the Today page.
 *
 * Child roles resolve a context in this order:
 *   clocked → next-action → quest-progress → idle
 * Parent role: queue(count) → all-clear.
 *
 * Props:
 *   role     : 'child' | 'parent'
 *   ctx      : { activeTimer, rpg, nextAction, activeQuest,
 *                weekday, dateStr, pendingCount,
 *                onCompleteChore, onTapHabit, onOpenHomework }
 *
 * `nextAction` is the top item from the backend's `next_actions` feed
 * (see apps/projects/priority.py). Its shape is the NextAction.as_dict()
 * serialization — {kind, id, title, subtitle, score, due_at, reward,
 * icon, tone, action_url}.
 */
export default function HeroPrimaryCard({ role = 'child', ctx = {} }) {
  const navigate = useNavigate();
  const { weekday, dateStr } = ctx;

  if (role === 'parent') {
    const count = Number(ctx.pendingCount) || 0;
    return (
      <motion.div variants={inkBleed} initial="initial" animate="animate">
        <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
          <div className="font-script text-sheikah-teal-deep text-sm mb-0.5">
            {weekday ? `${weekday} · ${dateStr}` : 'Today'}
          </div>
          {count > 0 ? (
            <>
              <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
                {count} {count === 1 ? 'thing needs' : 'things need'} your seal today
              </h1>
              <div className="font-body text-sm text-ink-secondary mt-1">
                Review duties, homework, and redemptions below.
              </div>
              <div className="mt-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    const el = document.getElementById('approval-queue');
                    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                  className={`${buttonPrimary} inline-flex items-center gap-2 px-4 py-2 text-sm`}
                >
                  <ClipboardCheck size={16} /> Review queue
                </button>
                <RuneBadge tone="ember">pending</RuneBadge>
              </div>
            </>
          ) : (
            <>
              <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
                Nothing needs your seal.
              </h1>
              <div className="font-body text-sm text-ink-secondary mt-1">
                A quiet page. The kids are on their own today.
              </div>
            </>
          )}
        </ParchmentCard>
      </motion.div>
    );
  }

  // Child contexts.
  const activeTimer = ctx.activeTimer;
  const nextAction = ctx.nextAction;
  const quest = ctx.activeQuest && ctx.activeQuest.status === 'active' ? ctx.activeQuest : null;

  let variant = 'idle';
  if (activeTimer) variant = 'clocked';
  else if (nextAction) variant = 'next-action';
  else if (quest) variant = 'quest-progress';

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate">
      <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
        <div className="font-script text-sheikah-teal-deep text-sm mb-0.5">
          {weekday ? `${weekday} · ${dateStr}` : 'Today'}
        </div>

        {variant === 'clocked' && (
          <>
            <div className="font-script text-xs text-ink-whisper uppercase tracking-wider">
              Still inking
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
              {activeTimer.project_title}
            </h1>
            <div className="font-rune text-3xl md:text-4xl font-bold text-ember-deep tabular-nums mt-2">
              {formatDuration(activeTimer.elapsed_minutes)}
            </div>
            <button
              type="button"
              onClick={() => navigate('/clock')}
              className={`${buttonPrimary} mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm`}
            >
              <Square size={16} /> Stop and log
            </button>
          </>
        )}

        {variant === 'next-action' && (
          <NextActionBody
            action={nextAction}
            onOpenHomework={ctx.onOpenHomework}
            onCompleteChore={ctx.onCompleteChore}
            onTapHabit={ctx.onTapHabit}
            onNavigate={navigate}
          />
        )}

        {variant === 'quest-progress' && (
          <>
            <div className="font-script text-xs text-royal uppercase tracking-wider">
              Active trial
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
              {quest.definition?.name}
            </h1>
            <div className="font-body text-sm text-ink-secondary mt-1">
              {quest.current_progress}/{quest.effective_target} · {quest.progress_percent}%
            </div>
            <div className="h-2 mt-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                style={{ width: `${Math.min(100, quest.progress_percent)}%` }}
              />
            </div>
            <button
              type="button"
              onClick={() => navigate('/quests')}
              className="mt-3 font-script text-sm text-sheikah-teal-deep hover:underline"
            >
              View quest →
            </button>
          </>
        )}

        {variant === 'idle' && (
          <>
            <div className="flex items-center gap-1.5 font-script text-xs text-ink-whisper uppercase tracking-wider">
              <Sparkles size={14} /> A quiet page
            </div>
            <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5">
              Nothing pressing — pick something.
            </h1>
            <button
              type="button"
              onClick={() => navigate('/quests')}
              className="mt-3 font-script text-sm text-sheikah-teal-deep hover:underline"
            >
              Open the quests hub →
            </button>
          </>
        )}
      </ParchmentCard>
    </motion.div>
  );
}

function NextActionBody({ action, onOpenHomework, onCompleteChore, onTapHabit, onNavigate }) {
  const Icon = ICON_MAP[action.icon] || Sparkles;
  const accentClass = TONE_TO_ACCENT_CLASS[action.tone] || 'text-moss';
  const buttonLabel = action.kind === 'homework' ? 'Submit'
    : action.kind === 'habit' ? 'Tap'
    : 'Complete';
  const handleClick = () => {
    if (action.kind === 'homework' && onOpenHomework) return onOpenHomework(action.id);
    if (action.kind === 'chore' && onCompleteChore) return onCompleteChore(action.id);
    if (action.kind === 'habit' && onTapHabit) return onTapHabit(action.id);
    if (action.action_url) onNavigate(action.action_url);
  };

  return (
    <>
      <div className={`flex items-center gap-1.5 font-script text-xs ${accentClass} uppercase tracking-wider`}>
        <Icon size={14} /> Next up
      </div>
      <h1 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 truncate">
        {action.title}
      </h1>
      <div className="font-body text-sm text-ink-secondary mt-1">
        {action.subtitle}
      </div>
      <button
        type="button"
        aria-label={`${buttonLabel} ${action.title}`}
        onClick={handleClick}
        className={`${buttonPrimary} mt-3 inline-flex items-center gap-2 px-4 py-2 text-sm`}
      >
        <Play size={16} /> {buttonLabel}
      </button>
    </>
  );
}

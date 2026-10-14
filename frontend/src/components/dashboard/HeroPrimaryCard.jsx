import usePrefersReducedMotion from '../../hooks/usePrefersReducedMotion';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Play, Square, Flame, Sparkles, ClipboardCheck, BookOpen } from 'lucide-react';
import ParchmentCard from '../journal/ParchmentCard';
import RuneBadge from '../journal/RuneBadge';
import IlluminatedVersal from '../atlas/IlluminatedVersal';
import { tierForProgress } from '../atlas/mastery.constants';
import { formatDuration } from '../../utils/format';
import { inkBleed } from '../../motion/variants';
import Button from '../Button';
import ProgressBar from '../ProgressBar';

const ICON_MAP = { BookOpen, Sparkles, Flame, Play, Square, ClipboardCheck };

const TONE_TO_ACCENT_CLASS = {
  royal: 'text-royal',
  moss: 'text-moss',
  ember: 'text-ember-deep',
};

// Drop-cap fill % for the hero's IlluminatedVersal. Different variants encode
// different progress signals — clocked uses elapsed minutes mod a one-hour
// ramp so the gilt slowly fills as the kid stays on task; quest-progress uses
// the quest's own % directly; next-action sits at a steady "just started"
// fill so the action reads as fresh.
function elapsedHourPct(minutes) {
  if (!minutes || minutes <= 0) return 5;
  return Math.min(100, (minutes % 60) * (100 / 60) + Math.min(60, minutes) * (40 / 60));
}

function versalProps({ letter, progressPct }) {
  const safe = Math.max(0, Math.min(100, progressPct));
  return {
    letter,
    progressPct: safe,
    tier: tierForProgress({ unlocked: safe > 0, progressPct: safe, level: 0 }),
    size: 'lg',
  };
}

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
  const reducedMotion = usePrefersReducedMotion();
  const reveal = reducedMotion
    ? { initial: false, animate: { opacity: 1, y: 0, filter: 'none' }, transition: { duration: 0 } }
    : { variants: inkBleed, initial: 'initial', animate: 'animate' };
  const navigate = useNavigate();
  const { weekday, dateStr } = ctx;

  if (role === 'parent') {
    const count = Number(ctx.pendingCount) || 0;
    // An empty queue while the aggregate is still in flight is "we don't know
    // yet", not "all clear" — claiming the queue is empty and then popping
    // into a full queue is how a glancing parent misses approvals.
    const settling = Boolean(ctx.loading) && count === 0;
    return (
      <motion.div {...reveal}>
        <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
          {!ctx.hideDate && <div className="font-script text-sheikah-teal-deep text-body mb-0.5">
            {weekday ? `${weekday} · ${dateStr}` : 'Today'}
          </div>}
          {count > 0 ? (
            <>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight break-words">
                {count} {count === 1 ? 'thing' : 'things'} to review today
              </h2>
              <div className="font-body text-body text-ink-secondary mt-1">
                A little encouragement goes a long way. Review completed work and rewards below.
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  onClick={() => {
                    const el = document.getElementById('approval-queue');
                    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
                    if (el) el.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
                  }}
                  className="inline-flex items-center gap-2"
                >
                  <ClipboardCheck size={16} /> Review approvals
                </Button>
                <RuneBadge tone="ember">pending</RuneBadge>
              </div>
            </>
          ) : settling ? (
            <>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight">
                Checking for updates…
              </h2>
              <div className="font-body text-body text-ink-secondary mt-1">
                Gathering completed work and reward requests.
              </div>
            </>
          ) : ctx.incomplete ? (
            <>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight">
                Some updates are unavailable
              </h2>
              <p className="font-body text-body text-ink-secondary mt-1">
                Retry to check the remaining approvals.
              </p>
            </>
          ) : (
            <>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight">
                You&apos;re all caught up.
              </h2>
              <div className="font-body text-body text-ink-secondary mt-1">
                Nothing is waiting for approval. Take a moment to see how everyone&apos;s doing.
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
    <motion.div {...reveal}>
      <ParchmentCard tone="bright" flourish className="relative overflow-hidden">
        {!ctx.hideDate && <div className="font-script text-sheikah-teal-deep text-body mb-0.5">
          {weekday ? `${weekday} · ${dateStr}` : 'Today'}
        </div>}

        {variant === 'clocked' && (
          <div className="flex items-start gap-3">
            <IlluminatedVersal
              {...versalProps({
                letter: activeTimer.project_title?.charAt(0) || '✦',
                progressPct: elapsedHourPct(activeTimer.elapsed_minutes),
              })}
            />
            <div className="min-w-0 flex-1">
              <div className="font-script text-caption text-ink-whisper uppercase tracking-wider">
                Time well spent
              </div>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 break-words">
                {activeTimer.project_title}
              </h2>
              <div className="font-rune text-3xl md:text-4xl font-bold text-ember-deep tabular-nums mt-2">
                {formatDuration(activeTimer.elapsed_minutes)}
              </div>
              <Button
                size="sm"
                onClick={() => navigate('/clock')}
                className="mt-3 inline-flex items-center gap-2"
              >
                <Square size={16} /> Stop and log
              </Button>
            </div>
          </div>
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
          <div className="flex items-start gap-3">
            <IlluminatedVersal
              {...versalProps({
                letter: quest.definition?.name?.charAt(0) || '✦',
                progressPct: quest.progress_percent || 0,
              })}
            />
            <div className="min-w-0 flex-1">
              <div className="font-script text-caption text-royal uppercase tracking-wider">
                Active challenge
              </div>
              <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 break-words">
                {quest.definition?.name}
              </h2>
              <div className="font-body text-body text-ink-secondary mt-1">
                {quest.current_progress}/{quest.effective_target} · {quest.progress_percent}%
              </div>
              <ProgressBar
                value={quest.progress_percent}
                max={100}
                aria-label={`${quest.definition?.name || 'Active challenge'} progress`}
                className="h-2 mt-2"
              />
              {/* Matches the Challenges tab in Tasks. */}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate('/trials')}
                className="mt-3 -ml-3 font-script text-body text-sheikah-teal-deep! hover:underline"
              >
                View challenge →
              </Button>
            </div>
          </div>
        )}

        {variant === 'idle' && (
          <>
            <div className="flex items-center gap-1.5 font-script text-caption text-ink-whisper uppercase tracking-wider">
              <Sparkles size={14} /> Room for something good
            </div>
            <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5">
              {ctx.idleTitle || 'Choose what you want to work on next.'}
            </h2>
            {ctx.idleDescription && <p className="font-body text-body text-ink-secondary mt-2">{ctx.idleDescription}</p>}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/quests')}
              className="mt-3 -ml-3 font-script text-body text-sheikah-teal-deep! hover:underline"
            >
              View tasks →
            </Button>
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
    <div className="flex items-start gap-3">
      <IlluminatedVersal
        {...versalProps({
          letter: action.title?.charAt(0) || '✦',
          progressPct: 20,
        })}
      />
      <div className="min-w-0 flex-1">
        <div className={`flex items-center gap-1.5 font-script text-caption ${accentClass} uppercase tracking-wider`}>
          <Icon size={14} /> Next up
        </div>
        <h2 className="font-body font-bold text-2xl md:text-3xl text-ink-primary leading-tight mt-0.5 break-words">
          {action.title}
        </h2>
        <div className="font-body text-body text-ink-secondary mt-1">
          {action.subtitle}
        </div>
        <Button
          size="sm"
          aria-label={`${buttonLabel} ${action.title}`}
          onClick={handleClick}
          className="mt-3 inline-flex items-center gap-2"
        >
          <Play size={16} /> {buttonLabel}
        </Button>
      </div>
    </div>
  );
}

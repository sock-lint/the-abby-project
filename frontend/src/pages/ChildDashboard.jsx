import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import PageShell from '../components/layout/PageShell';
import * as Sentry from '@sentry/react';
import {
  completeChore, getCoinSummaryByDay, getRecentDrops,
  getStable, logHabitTap,
} from '../api';
import { hapticTap } from '../utils/haptics';
import { useApi } from '../hooks/useApi';
import { formatCurrency } from '../utils/format';
import ParchmentCard from '../components/journal/ParchmentCard';
import QuestLogEntry from '../components/journal/QuestLogEntry';
import DeckleDivider from '../components/journal/DeckleDivider';
import RuneBadge from '../components/journal/RuneBadge';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import VitalPipStrip from '../components/dashboard/VitalPipStrip';
import AccordionSection from '../components/dashboard/AccordionSection';
import DailyChallengeCard from '../components/dashboard/DailyChallengeCard';
import SinceLastVisitCard from '../components/dashboard/SinceLastVisitCard';
import StreakAtRiskBanner from '../components/dashboard/StreakAtRiskBanner';
import HomeworkSubmitSheet from '../components/HomeworkSubmitSheet';
import IconButton from '../components/IconButton';
import PageHeader from '../components/layout/PageHeader';
import ProgressBar from '../components/ProgressBar';
import StarRating from '../components/StarRating';
import Button from '../components/Button';
import ErrorAlert from '../components/ErrorAlert';
import ScrollRail from '../components/ScrollRail';
import SectionHeader from '../components/SectionHeader';
import Sparkline from '../components/Sparkline';
import { CoinIcon, TreasuryIcon } from '../components/icons/JournalIcons';
import { BookOpen, Sparkles, Flame, Target, X, Award } from 'lucide-react';
import { RARITY_COLORS } from '../constants/colors';
import { staggerChildren, staggerItem, inkBleed } from '../motion/variants';
import { formatWeekdayDate, mapProjectTone } from './_dashboardShared';
import CatalogIcon from '../components/rpg/CatalogIcon';
import BadgeArtwork from '../components/atlas/BadgeArtwork';
import WellbeingCard from './dashboard/WellbeingCard';
import useChallenges from '../hooks/useChallenges';
import PinnedChallengeCard from '../components/dashboard/PinnedChallengeCard';
import ExploreChallengesLink from '../components/dashboard/ExploreChallengesLink';

const VISIBLE_LOG_CAP = 5;

// Map NextAction.icon names to lucide-react components for the quest log row
// glyph. Falls back to Sparkles if the backend ships an unknown name.
const ICON_MAP = { BookOpen, Sparkles, Flame };

// Map NextAction.kind to the kind-tag label shown in the QuestLogEntry.
const KIND_LABEL = { homework: 'Homework', chore: 'Chore', habit: 'Habit' };

export default function ChildDashboard({ data, reload }) {
  const { data: recentDrops, error: dropsError, reload: reloadDrops } = useApi(getRecentDrops);
  const { data: stableData } = useApi(getStable);
  const { data: challenges, pinnedGoal, loading: challengesLoading, error: challengesError, reload: reloadChallenges } = useChallenges({ refreshKey: data });
  const { data: coinSummary } = useApi(getCoinSummaryByDay);
  const navigate = useNavigate();
  const [logExpanded, setLogExpanded] = useState(false);
  const [activeHomework, setActiveHomework] = useState(null);

  const {
    active_timer, current_balance, coin_balance, this_week, active_projects,
    recent_badges, savings_goals, rpg, next_actions = [], since_last_visit,
  } = data || {};

  const activePet = stableData?.pets?.find((p) => p.is_active) || null;

  // Audit M8: surface fast-action errors instead of silently swallowing
  // them. Pre-fix, ``.catch(() => {})`` masked 400s ("you've already
  // tapped this habit today"), 403s ("locked"), and 5xxs alike — the
  // user clicked, nothing happened, and operators had no signal.
  // ``actionError`` flips into a soft inline banner; everything also
  // hits Sentry so prod regressions are visible.
  const [actionError, setActionError] = useState('');
  const [completedIds, setCompletedIds] = useState(new Set());
  const handleActionError = useCallback((err, label) => {
    Sentry.captureException(err, { extra: { handler: label } });
    setActionError(err?.response?.error || err?.message || `${label} failed.`);
  }, []);

  const handleCompleteChore = useCallback(
    (id) => {
      hapticTap();
      setCompletedIds((prev) => new Set(prev).add(`chore-${id}`));
      return completeChore(id)
        .then(reload)
        .catch((err) => {
          setCompletedIds((prev) => {
            const next = new Set(prev);
            next.delete(`chore-${id}`);
            return next;
          });
          handleActionError(err, 'Mark chore done');
        });
    },
    [reload, handleActionError],
  );
  const handleTapHabit = useCallback(
    (id) => {
      hapticTap();
      setCompletedIds((prev) => new Set(prev).add(`habit-${id}`));
      return logHabitTap(id, 1)
        .then(reload)
        .catch((err) => {
          setCompletedIds((prev) => {
            const next = new Set(prev);
            next.delete(`habit-${id}`);
            return next;
          });
          handleActionError(err, 'Log habit');
        });
    },
    [reload, handleActionError],
  );
  // Open the homework submit sheet inline. We accept either a plain id
  // (from the hero's NextAction handler) or an action object (from the
  // quest log row); the sheet only needs `{id, title}`.
  const handleOpenHomework = (idOrAction) => {
    if (idOrAction && typeof idOrAction === 'object') {
      setActiveHomework(idOrAction);
    } else {
      const match = (next_actions || []).find(
        (a) => a.kind === 'homework' && a.id === idOrAction,
      );
      setActiveHomework(match || { id: idOrAction });
    }
  };

  // The server ranks work across all kinds. Apply the cap to that order so
  // later homework cannot push today's chores or habits out of view.
  const taskActions = next_actions.filter((action) => KIND_LABEL[action.kind]);
  const totalLogCount = taskActions.length;
  const visibleActions = logExpanded ? taskActions : taskActions.slice(0, VISIBLE_LOG_CAP);

  const onActionClick = (a) => {
    if (a.kind === 'homework') return handleOpenHomework(a);
    if (a.kind === 'chore') return handleCompleteChore(a.id);
    if (a.kind === 'habit') return handleTapHabit(a.id);
  };

  const { weekday, dateStr } = formatWeekdayDate();

  return (
    <PageShell variants={inkBleed}>
      <PageHeader
        title="Today"
        kicker={`${weekday} · ${dateStr}`}
      />

      {actionError && (
        // Audit M8: surface fast-action errors. Auto-dismissable so a
        // stale message doesn't hang around when the next action succeeds.
        <div
          role="alert"
          className="rounded-lg border border-rose/40 bg-rose/10 px-4 py-2 text-body text-rose flex items-start gap-3"
        >
          <span className="flex-1">{actionError}</span>
          <IconButton
            size="sm"
            onClick={() => setActionError('')}
            aria-label="Dismiss error"
            className="text-rose/70! hover:text-rose!"
          >
            <X size={16} />
          </IconButton>
        </div>
      )}

      <HeroPrimaryCard
        role="child"
        ctx={{
          activeTimer: active_timer,
          rpg,
          nextAction: next_actions[0] || null,
          weekday, dateStr,
          hideDate: true,
          idleTitle: 'No urgent tasks right now',
          idleDescription: 'View all tasks for upcoming work. Submitted work may still be waiting for review.',
          onCompleteChore: handleCompleteChore,
          onTapHabit: handleTapHabit,
          onOpenHomework: handleOpenHomework,
        }}
      />

      <StreakAtRiskBanner rpg={rpg} />

      {totalLogCount > 0 && (
        <section aria-label="Your tasks">
          <SectionHeader title="Your tasks" count={totalLogCount} kicker="Most urgent first" className="mb-3" />
          <ParchmentCard flourish>
            <ul className="space-y-2">
              {visibleActions.map((action) => {
                const Icon = ICON_MAP[action.icon] || Sparkles;
                const parts = [];
                if (action.reward?.money && action.reward.money !== '0.00') parts.push(`$${action.reward.money}`);
                if (action.reward?.coins) parts.push(`${action.reward.coins}🪙`);
                return (
                  <QuestLogEntry
                    key={`${action.kind}-${action.id}`}
                    title={action.title}
                    meta={action.subtitle}
                    reward={parts.length ? parts.join(' · ') : null}
                    status={completedIds.has(`${action.kind}-${action.id}`) ? 'done' : 'pending'}
                    kind={KIND_LABEL[action.kind]}
                    tone={action.tone}
                    icon={<Icon size={16} />}
                    onAction={() => onActionClick(action)}
                  />
                );
              })}
            </ul>
            {totalLogCount > VISIBLE_LOG_CAP && (
              <div className="mt-3">
                <Button variant="ghost" size="sm" onClick={() => setLogExpanded((v) => !v)}>
                  {logExpanded ? 'Show fewer' : `Show all ${totalLogCount} tasks →`}
                </Button>
              </div>
            )}
          </ParchmentCard>
        </section>
      )}

      {active_projects?.length > 0 && (
        <section aria-label="Continue a project">
          <SectionHeader title="Continue a project" count={active_projects.length} className="mb-3" />
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {active_projects.map((p) => (
              <motion.button
                key={p.id}
                type="button"
                whileHover={{ y: -2 }}
                onClick={() => navigate(`/quests/ventures/${p.id}`)}
                className="text-left"
              >
                <ParchmentCard>
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <div className="min-w-0 font-body font-bold text-lg leading-tight break-words">{p.title}</div>
                    <RuneBadge tone={mapProjectTone(p.status)} size="sm">
                      {p.status.replace('_', ' ')}
                    </RuneBadge>
                  </div>
                  <div className="flex flex-wrap items-center gap-1 font-body text-caption text-ink-secondary mb-3">
                    <span aria-hidden="true">Difficulty:</span>
                    <StarRating value={p.difficulty || 1} />
                  </div>
                  {p.milestones_total > 0 && (
                    <>
                      <div className="flex justify-between font-rune text-tiny text-ink-whisper mb-1">
                        <span>MILESTONES</span>
                        <span>{p.milestones_completed}/{p.milestones_total}</span>
                      </div>
                      <ProgressBar
                        value={p.milestones_completed}
                        max={p.milestones_total}
                        aria-label={`${p.title} milestones`}
                        className="h-1.5"
                      />
                    </>
                  )}
                </ParchmentCard>
              </motion.button>
            ))}
          </div>
        </section>
      )}

      <ErrorAlert message={challengesError} />
      {challengesError && <Button variant="secondary" onClick={reloadChallenges}>Retry challenges</Button>}
      {!challengesLoading && (!challengesError || pinnedGoal) && <PinnedChallengeCard goal={pinnedGoal} />}
      {!challengesLoading && !challengesError && <ExploreChallengesLink goals={challenges?.results || []} pinnedGoal={pinnedGoal} />}

      <DeckleDivider glyph="flourish-corner" />

      <WellbeingCard />

      <SinceLastVisitCard summary={since_last_visit} />

      <VitalPipStrip
        coinBalance={coin_balance}
        loginStreak={rpg?.login_streak}
        level={rpg?.level}
        activePet={activePet}
      />

      <AccordionSection
        index={0}
        title="Rewards & earnings"
        kicker="this week at a glance"
        icon={<TreasuryIcon size={18} />}
        tone="gold"
        peek={`${formatCurrency(current_balance)} · ${coin_balance ?? 0} coins · ${this_week?.hours_worked ?? 0}h${challenges?.daily_bonus?.awarded ? " · Daily bonus earned" : ""}`}
      >
        <motion.div variants={staggerChildren} initial="initial" animate="animate" className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3">
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=coffers')}
            aria-label={`Money owed ${formatCurrency(current_balance)} — open payments`}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="font-script text-caption uppercase tracking-wider text-moss">Money owed</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{formatCurrency(current_balance)}</div>
          </motion.button>
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=bazaar')}
            aria-label={`${coin_balance ?? 0} coins — open reward shop`}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="flex items-center gap-1 font-script text-caption uppercase tracking-wider text-gold-leaf">
              <CoinIcon size={14} aria-hidden="true" /> Coins
            </div>
            <div className="font-display text-xl font-semibold text-ink-primary">{coin_balance ?? 0}</div>
          </motion.button>
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=wages')}
            aria-label={`${this_week?.hours_worked ?? 0} hours clocked this week — open timecards`}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="font-script text-caption uppercase tracking-wider text-sheikah-teal-deep">Hours this week</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{this_week?.hours_worked ?? 0}h</div>
          </motion.button>
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/payments')}
            aria-label={`Earned this week ${formatCurrency(this_week?.earnings)} — open payments ledger`}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="font-script text-caption uppercase tracking-wider text-ember-deep">Earned this week</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{formatCurrency(this_week?.earnings)}</div>
          </motion.button>
        </motion.div>
        <div className="mt-3">
          <DailyChallengeCard challenge={challenges?.daily_bonus ?? null} />
        </div>
        {coinSummary?.series?.some((p) => p.earned > 0) && (
          <div className="mt-3">
            <div className="font-script text-caption uppercase tracking-wider text-gold-leaf mb-1">
              Coins earned · last 30 days
            </div>
            <Sparkline
              data={coinSummary.series.map((p) => p.earned)}
              label="Coins earned per day over the last 30 days"
              strokeClass="stroke-gold-leaf"
            />
          </div>
        )}
        <div className="font-script text-caption text-ink-whisper mt-3 leading-relaxed">
          money owed: earned money still owed by your parent · coins: earned across all your work, spent in the reward shop · hours and earnings: this week's clocked time
        </div>
      </AccordionSection>

      {dropsError && !recentDrops && (
        <ErrorAlert message="Couldn't load recent drops." onRetry={reloadDrops} />
      )}

      {recentDrops?.length > 0 && (
        <section aria-label="Recent items">
          <SectionHeader
            title="Recent items"
            kicker="Items earned through your activity"
            className="mb-3"
          />
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {recentDrops.map((d) => (
              <motion.button
                key={d.id}
                type="button"
                whileHover={{ y: -2 }}
                onClick={() => navigate('/treasury?tab=satchel')}
                aria-label={`${d.item_name}${d.quantity > 1 ? ` × ${d.quantity}` : ''}${d.was_salvaged ? ' (converted to coins)' : ''} — open inventory`}
                className={`min-w-0 p-3 rounded-2xl border text-center hover:brightness-105 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-royal transition-[filter] ${RARITY_COLORS[d.item_rarity] || 'bg-ink-page-aged border-ink-page-shadow'}`}
              >
                <div className="flex h-10 items-center justify-center mb-2">
                  <CatalogIcon assetId={d.item_catalog_icon} spriteKey={d.item_sprite_key} icon={d.item_icon || '📦'} size={40} alt={d.item_name} />
                </div>
                <div className="font-body text-body font-semibold text-ink-primary break-words leading-snug">
                  {d.item_name}{d.quantity > 1 && <span> × {d.quantity}</span>}
                </div>
                {d.was_salvaged && (
                  <div className="font-body text-caption text-ink-secondary mt-1">Converted to coins</div>
                )}
              </motion.button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/treasury?tab=satchel')}
            className="mt-2 -ml-3 text-sheikah-teal-deep!"
          >
            View inventory →
          </Button>
        </section>
      )}

      {savings_goals?.length > 0 && (
        <AccordionSection
          index={2}
          title="Savings goals"
          kicker="Track what you are saving for"
          icon={<Target size={18} />}
          tone="moss"
          count={savings_goals.length}
          peek={`${savings_goals[0]?.title} · ${savings_goals[0]?.percent_complete ?? 0}%`}
        >
          <div className="grid md:grid-cols-2 gap-3">
            {savings_goals.slice(0, 2).map((goal) => (
              <button
                key={goal.id}
                type="button"
                onClick={() => navigate('/treasury?tab=hoards')}
                className="text-left"
              >
                <ParchmentCard seal className="hover:brightness-105 transition-[filter]">
                  <div className="flex items-center gap-2 mb-2">
                    {goal.icon && <span className="text-xl">{goal.icon}</span>}
                    <Target size={16} className="text-moss shrink-0" />
                    <span className="font-display text-base leading-tight truncate">
                      {goal.title}
                    </span>
                  </div>
                  <div className="flex justify-between font-rune text-tiny text-ink-whisper mb-1">
                    <span>{formatCurrency(goal.current_amount)}</span>
                    <span>{formatCurrency(goal.target_amount)}</span>
                  </div>
                  <ProgressBar
                    value={goal.percent_complete}
                    max={100}
                    color="bg-moss"
                    aria-label={`${goal.title} savings progress`}
                  />
                </ParchmentCard>
              </button>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/treasury?tab=hoards')}
            className="mt-3 -ml-3 font-script text-caption text-sheikah-teal-deep! hover:underline"
          >
            View all savings goals →
          </Button>
        </AccordionSection>
      )}

      {recent_badges?.length > 0 && (
        <AccordionSection
          index={3}
          title="Recent badges"
          kicker="badges earned"
          icon={<Award size={18} />}
          tone="ember"
          count={recent_badges.length}
          peek={`${recent_badges.length} badge${recent_badges.length !== 1 ? 's' : ''} · latest: ${recent_badges[0]?.badge__name}`}
        >
          <ScrollRail>
            {recent_badges.map((b, i) => (
              <motion.button
                key={b.badge__id}
                type="button"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => navigate('/atlas?tab=badges')}
                aria-label={`${b.badge__name} — view earned badges`}
                className="shrink-0 w-28 text-center p-3 rounded-xl bg-ink-page-aged border border-ink-page-shadow hover:border-gold-leaf/60 transition-colors"
              >
                <div className="flex justify-center mb-1"><BadgeArtwork earned badge={{
                  name: b.badge__name, icon: b.badge__icon, catalog_icon: b.badge__catalog_icon,
                }} /></div>
                <div className="font-body text-caption font-semibold break-words leading-snug">{b.badge__name}</div>
              </motion.button>
            ))}
          </ScrollRail>
        </AccordionSection>
      )}

      <HomeworkSubmitSheet
        assignment={activeHomework}
        onClose={() => setActiveHomework(null)}
        onSubmitted={() => {
          setActiveHomework(null);
          reload();
        }}
      />

    </PageShell>
  );
}

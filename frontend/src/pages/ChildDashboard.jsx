import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import {
  completeChore, getActiveQuest, getRecentDrops, getStable, logHabitTap,
} from '../api';
import { useApi } from '../hooks/useApi';
import { formatCurrency } from '../utils/format';
import ParchmentCard from '../components/journal/ParchmentCard';
import QuestLogEntry from '../components/journal/QuestLogEntry';
import DeckleDivider from '../components/journal/DeckleDivider';
import RuneBadge from '../components/journal/RuneBadge';
import HeroPrimaryCard from '../components/dashboard/HeroPrimaryCard';
import VitalPipStrip from '../components/dashboard/VitalPipStrip';
import AccordionSection from '../components/dashboard/AccordionSection';
import HomeworkSubmitSheet from '../components/HomeworkSubmitSheet';
import { CoinIcon } from '../components/icons/JournalIcons';
import { BookOpen, Sparkles, Flame, Target } from 'lucide-react';
import { RARITY_RING_COLORS } from '../constants/colors';
import { staggerChildren, staggerItem, inkBleed } from '../motion/variants';
import { formatWeekdayDate, mapProjectTone } from './_dashboardShared';

const VISIBLE_LOG_CAP = 5;

// Map NextAction.icon names to lucide-react components for the quest log row
// glyph. Falls back to Sparkles if the backend ships an unknown name.
const ICON_MAP = { BookOpen, Sparkles, Flame };

// Map NextAction.kind to the kind-tag label shown in the QuestLogEntry.
const KIND_LABEL = { homework: 'Study', chore: 'Duty', habit: 'Ritual' };

/**
 * Group the next_actions feed into the three quest-log sections. The
 * backend already sorts by score DESC with deterministic tie-breaking, so
 * each section preserves the global ranking.
 */
function buildQuestLogFromActions(next_actions = []) {
  const study = [];
  const duty = [];
  const ritual = [];
  for (const a of next_actions) {
    if (a.kind === 'homework') study.push(a);
    else if (a.kind === 'chore') duty.push(a);
    else if (a.kind === 'habit') ritual.push(a);
  }
  return { study, duty, ritual };
}

export default function ChildDashboard({ data, reload }) {
  const { data: recentDrops } = useApi(getRecentDrops);
  const { data: stableData } = useApi(getStable);
  const { data: activeQuest } = useApi(getActiveQuest);
  const navigate = useNavigate();
  const [logExpanded, setLogExpanded] = useState(false);
  const [activeHomework, setActiveHomework] = useState(null);

  const {
    active_timer, current_balance, coin_balance, this_week, active_projects,
    recent_badges, savings_goals, rpg, next_actions = [],
  } = data || {};

  const activePet = stableData?.pets?.find((p) => p.is_active) || null;

  const handleCompleteChore = (id) => completeChore(id).then(reload).catch(() => {});
  const handleTapHabit = (id) => logHabitTap(id, 1).then(reload).catch(() => {});
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

  const { study, duty, ritual } = buildQuestLogFromActions(next_actions);
  const sections = [
    { key: 'study', label: 'Study', tone: 'royal', actions: study },
    { key: 'duty', label: 'Duty', tone: 'moss', actions: duty },
    { key: 'ritual', label: 'Ritual', tone: 'gold', actions: ritual },
  ].filter((s) => s.actions.length > 0);

  const totalLogCount = study.length + duty.length + ritual.length;
  const visibleSections = (() => {
    if (logExpanded) return sections;
    let remaining = VISIBLE_LOG_CAP;
    const out = [];
    for (const s of sections) {
      if (remaining <= 0) break;
      const slice = s.actions.slice(0, remaining);
      remaining -= slice.length;
      out.push({ ...s, actions: slice });
    }
    return out;
  })();
  const visibleCount = visibleSections.reduce((n, s) => n + s.actions.length, 0);
  const hiddenQuestCount = totalLogCount - visibleCount;

  const onActionClick = (a) => {
    if (a.kind === 'homework') return handleOpenHomework(a);
    if (a.kind === 'chore') return handleCompleteChore(a.id);
    if (a.kind === 'habit') return handleTapHabit(a.id);
  };

  const { weekday, dateStr } = formatWeekdayDate();

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate" className="max-w-6xl mx-auto space-y-5">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
          {weekday} · {dateStr} · to be inked before nightfall
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Today&apos;s Entry
        </h1>
      </header>

      <HeroPrimaryCard
        role="child"
        ctx={{
          activeTimer: active_timer,
          rpg,
          nextAction: next_actions[0] || null,
          activeQuest,
          weekday, dateStr,
          onCompleteChore: handleCompleteChore,
          onTapHabit: handleTapHabit,
          onOpenHomework: handleOpenHomework,
        }}
      />

      <VitalPipStrip
        coinBalance={coin_balance}
        loginStreak={rpg?.login_streak}
        level={rpg?.level}
        activePet={activePet}
      />

      {totalLogCount > 0 && (
        <section>
          <div className="mb-2 flex justify-end">
            <RuneBadge tone="teal" size="sm">{totalLogCount}</RuneBadge>
          </div>
          <ParchmentCard flourish>
            <div className="space-y-3">
              {visibleSections.map((section) => (
                <div key={section.key}>
                  <div className="font-script text-xs text-ink-whisper uppercase tracking-wider mb-1">
                    {section.label}
                  </div>
                  <ul className="space-y-2">
                    {section.actions.map((a) => {
                      const Icon = ICON_MAP[a.icon] || Sparkles;
                      const meta = a.subtitle;
                      let reward = null;
                      if (a.reward) {
                        const parts = [];
                        if (a.reward.money && a.reward.money !== '0.00') parts.push(`$${a.reward.money}`);
                        if (a.reward.coins) parts.push(`${a.reward.coins}🪙`);
                        if (parts.length) reward = parts.join(' · ');
                      }
                      return (
                        <QuestLogEntry
                          key={`${a.kind}-${a.id}`}
                          title={a.title}
                          meta={meta}
                          reward={reward}
                          status="pending"
                          kind={KIND_LABEL[a.kind] || section.label}
                          tone={a.tone || section.tone}
                          icon={<Icon size={16} />}
                          onAction={() => onActionClick(a)}
                        />
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
            {hiddenQuestCount > 0 && (
              <button
                type="button"
                onClick={() => setLogExpanded(true)}
                className="mt-3 font-script text-sm text-sheikah-teal-deep hover:underline"
              >
                Show {hiddenQuestCount} more →
              </button>
            )}
          </ParchmentCard>
        </section>
      )}

      <DeckleDivider glyph="flourish-corner" />

      {recentDrops?.length > 0 && (
        <section>
          <div className="mb-2">
            <div className="font-script text-sheikah-teal-deep text-sm">drops from the last two days</div>
            <h2 className="font-display text-xl md:text-2xl text-ink-primary leading-tight">Recent Loot</h2>
          </div>
          <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
            {recentDrops.map((d) => (
              <motion.button
                key={d.id}
                type="button"
                whileHover={{ y: -2 }}
                onClick={() => navigate('/bestiary?tab=satchel')}
                className={`shrink-0 w-24 p-3 rounded-xl bg-ink-page-aged border border-ink-page-shadow text-center ring-2 ring-offset-2 ring-offset-ink-page ${RARITY_RING_COLORS[d.rarity] || 'ring-transparent'}`}
              >
                <div className="text-3xl mb-1">{d.item_icon || '📦'}</div>
                <div className="font-body text-xs font-medium truncate">{d.item_name}</div>
                {d.was_salvaged && (
                  <div className="font-script text-micro text-gold-leaf mt-0.5">salvaged</div>
                )}
              </motion.button>
            ))}
          </div>
        </section>
      )}

      <AccordionSection
        title="Treasury"
        kicker="this week at a glance"
        peek={`${formatCurrency(current_balance)} · ${coin_balance ?? 0} coins · ${this_week?.hours_worked ?? 0}h`}
      >
        <motion.div variants={staggerChildren} initial="initial" animate="animate" className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=coffers')}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="font-script text-xs uppercase tracking-wider text-moss">Balance</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{formatCurrency(current_balance)}</div>
          </motion.button>
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=bazaar')}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="flex items-center gap-1 font-script text-xs uppercase tracking-wider text-gold-leaf">
              <CoinIcon size={14} /> Coins
            </div>
            <div className="font-display text-xl font-semibold text-ink-primary">{coin_balance ?? 0}</div>
          </motion.button>
          <motion.button
            variants={staggerItem}
            type="button"
            onClick={() => navigate('/treasury?tab=wages')}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3 hover:bg-ink-page-rune-glow transition-colors"
          >
            <div className="font-script text-xs uppercase tracking-wider text-sheikah-teal-deep">Hours this week</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{this_week?.hours_worked ?? 0}h</div>
          </motion.button>
          <motion.div
            variants={staggerItem}
            className="text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3"
          >
            <div className="font-script text-xs uppercase tracking-wider text-ember-deep">Earned this week</div>
            <div className="font-display text-xl font-semibold text-ink-primary">{formatCurrency(this_week?.earnings)}</div>
          </motion.div>
        </motion.div>
      </AccordionSection>

      {active_projects?.length > 0 && (
        <AccordionSection
          title="Next Up"
          kicker="ventures under way"
          count={active_projects.length}
          peek={active_projects[0]?.title}
        >
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
                    <div className="font-display text-lg leading-tight truncate">{p.title}</div>
                    <RuneBadge tone={mapProjectTone(p.status)} size="sm">
                      {p.status.replace('_', ' ')}
                    </RuneBadge>
                  </div>
                  <div className="font-script text-xs text-ink-whisper mb-3">
                    difficulty: {'★'.repeat(p.difficulty || 1)}
                  </div>
                  {p.milestones_total > 0 && (
                    <>
                      <div className="flex justify-between font-rune text-tiny text-ink-whisper mb-1">
                        <span>MILESTONES</span>
                        <span>{p.milestones_completed}/{p.milestones_total}</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                          style={{ width: `${(p.milestones_completed / p.milestones_total) * 100}%` }}
                        />
                      </div>
                    </>
                  )}
                </ParchmentCard>
              </motion.button>
            ))}
          </div>
        </AccordionSection>
      )}

      {savings_goals?.length > 0 && (
        <AccordionSection
          title="Hoard"
          kicker="treasure chests in progress"
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
                  <div className="h-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-moss to-gold-leaf"
                      style={{ width: `${goal.percent_complete}%` }}
                    />
                  </div>
                </ParchmentCard>
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => navigate('/treasury?tab=hoards')}
            className="mt-3 font-script text-caption text-sheikah-teal-deep hover:text-sheikah-teal-deep/80"
          >
            View all in Treasury →
          </button>
        </AccordionSection>
      )}

      {recent_badges?.length > 0 && (
        <AccordionSection
          title="Recent Accolades"
          kicker="badges earned"
          count={recent_badges.length}
          peek={recent_badges[0]?.badge__name}
        >
          <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
            {recent_badges.map((b, i) => (
              <motion.button
                key={i}
                type="button"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => navigate('/atlas?tab=skills')}
                className="shrink-0 w-28 text-center p-3 rounded-xl bg-ink-page-aged border border-ink-page-shadow hover:border-gold-leaf/60 transition-colors"
              >
                <div className="text-4xl mb-1">{b.badge__icon || '🏅'}</div>
                <div className="font-body text-xs font-medium truncate">{b.badge__name}</div>
              </motion.button>
            ))}
          </div>
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

    </motion.div>
  );
}

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
import { DragonIcon, InkwellIcon, ScrollIcon, CoinIcon } from '../components/icons/JournalIcons';
import { Target } from 'lucide-react';
import { RARITY_RING_COLORS } from '../constants/colors';
import { staggerChildren, staggerItem, inkBleed } from '../motion/variants';
import { formatWeekdayDate, mapProjectTone } from './_dashboardShared';

const VISIBLE_LOG_CAP = 5;

function buildTodayQuests({ chores_today, activeQuest, rpg, activeTimer, onTapHabit, onCompleteChore }) {
  const out = [];
  if (activeTimer?.project_title) {
    out.push({
      id: `active-${activeTimer.project_id}`,
      title: `Keep inking: ${activeTimer.project_title}`,
      meta: 'Clocked in',
      status: 'pending',
      kind: 'venture',
      tone: 'teal',
      icon: <InkwellIcon size={16} />,
    });
  }
  if (activeQuest && activeQuest.status === 'active') {
    const t = activeQuest.definition;
    out.push({
      id: `quest-${activeQuest.id}`,
      title: t.name,
      meta: `${t.quest_type === 'boss' ? 'Boss' : 'Collection'} · ${activeQuest.progress_percent}% · ${activeQuest.current_progress}/${activeQuest.effective_target}`,
      status: 'pending',
      kind: 'trial',
      tone: 'royal',
      icon: <DragonIcon size={16} />,
    });
  }
  (chores_today || []).forEach((c) => {
    out.push({
      id: `chore-${c.id}`,
      title: c.title,
      meta: c.reward_amount ? `ritual · $${c.reward_amount}` : 'ritual',
      reward: c.is_done ? null : c.coin_reward ? `$${c.reward_amount} · ${c.coin_reward}🪙` : `$${c.reward_amount}`,
      status: c.is_done ? 'done' : 'pending',
      kind: 'ritual',
      tone: 'moss',
      icon: c.icon ? <span className="text-base">{c.icon}</span> : null,
      onAction: c.is_done ? undefined : () => onCompleteChore(c.id),
    });
  });
  (rpg?.habits_today || []).slice(0, 5).forEach((h) => {
    const cap = h.max_taps_per_day ?? 1;
    const taps = h.taps_today ?? 0;
    const atCap = taps >= cap;
    out.push({
      id: `habit-${h.id}`,
      title: h.name,
      meta: `habit · strength ${h.strength ?? 0} · ${taps}/${cap} today`,
      status: atCap ? 'done' : 'pending',
      kind: 'virtue',
      tone: 'gold',
      icon: h.icon ? <span className="text-base">{h.icon}</span> : <ScrollIcon size={16} />,
      onAction: atCap ? undefined : () => onTapHabit(h.id),
    });
  });
  return out;
}

export default function ChildDashboard({ data, reload }) {
  const { data: recentDrops } = useApi(getRecentDrops);
  const { data: stableData } = useApi(getStable);
  const { data: activeQuest } = useApi(getActiveQuest);
  const navigate = useNavigate();
  const [logExpanded, setLogExpanded] = useState(false);

  const {
    active_timer, current_balance, coin_balance, this_week, active_projects,
    recent_badges, savings_goals, chores_today, rpg,
  } = data || {};

  const activePet = stableData?.pets?.find((p) => p.is_active) || null;

  const onCompleteChore = (id) => completeChore(id).then(reload).catch(() => {});
  const onTapHabit = (id) => logHabitTap(id, 1).then(reload).catch(() => {});

  const todayQuests = buildTodayQuests({
    chores_today, activeQuest, rpg, activeTimer: active_timer, onTapHabit, onCompleteChore,
  });
  const visibleQuests = logExpanded ? todayQuests : todayQuests.slice(0, VISIBLE_LOG_CAP);
  const hiddenQuestCount = todayQuests.length - visibleQuests.length;

  const { weekday, dateStr } = formatWeekdayDate();

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate" className="max-w-6xl mx-auto space-y-5">
      <header>
        <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
          {weekday} · {dateStr}
        </div>
        <h1 className="font-display italic text-3xl md:text-4xl text-ink-primary leading-tight">
          Today&apos;s Entry
        </h1>
      </header>

      <HeroPrimaryCard
        role="child"
        ctx={{
          activeTimer: active_timer,
          rpg, chores_today,
          activeQuest,
          weekday, dateStr,
          onCompleteChore,
          onTapHabit,
        }}
      />

      <VitalPipStrip
        coinBalance={coin_balance}
        loginStreak={rpg?.login_streak}
        level={rpg?.level}
        activePet={activePet}
      />

      {todayQuests.length > 0 && (
        <section>
          <div className="mb-2 flex items-end justify-between gap-3">
            <div>
              <div className="font-script text-sheikah-teal-deep text-sm">to be inked before nightfall</div>
              <h2 className="font-display text-xl md:text-2xl text-ink-primary leading-tight">
                Today&apos;s Log
              </h2>
            </div>
            <RuneBadge tone="teal" size="sm">{todayQuests.length}</RuneBadge>
          </div>
          <ParchmentCard flourish>
            <ul className="space-y-2">
              {visibleQuests.map((q) => (
                <QuestLogEntry
                  key={q.id}
                  title={q.title}
                  meta={q.meta}
                  reward={q.reward}
                  status={q.status}
                  kind={q.kind}
                  tone={q.tone}
                  icon={q.icon}
                  onAction={q.onAction}
                />
              ))}
            </ul>
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
                  <div className="font-script text-[10px] text-gold-leaf mt-0.5">salvaged</div>
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
                      <div className="flex justify-between font-rune text-[11px] text-ink-whisper mb-1">
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
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {savings_goals.map((goal) => (
              <ParchmentCard key={goal.id} seal>
                <div className="flex items-center gap-2 mb-2">
                  {goal.icon && <span className="text-xl">{goal.icon}</span>}
                  <Target size={16} className="text-moss shrink-0" />
                  <span className="font-display text-base leading-tight truncate">
                    {goal.title}
                  </span>
                </div>
                <div className="flex justify-between font-rune text-[11px] text-ink-whisper mb-1">
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
            ))}
          </div>
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

    </motion.div>
  );
}

import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ClipboardCheck, BookOpen, Target, Sparkles } from 'lucide-react';
import {
  getActiveQuest, getDashboard, getRecentDrops, getStable,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useAuth } from '../hooks/useApi';
import { formatCurrency, formatDuration } from '../utils/format';
import Loader from '../components/Loader';
import ErrorAlert from '../components/ErrorAlert';
import ParchmentCard from '../components/journal/ParchmentCard';
import QuestLogEntry from '../components/journal/QuestLogEntry';
import StreakFlame from '../components/journal/StreakFlame';
import PartyCard from '../components/journal/PartyCard';
import RuneBand from '../components/journal/RuneBand';
import RuneBadge from '../components/journal/RuneBadge';
import DeckleDivider from '../components/journal/DeckleDivider';
import {
  DragonIcon, InkwellIcon, ScrollIcon, CoinIcon, EggIcon,
} from '../components/icons/JournalIcons';
import { RARITY_RING_COLORS } from '../constants/colors';
import { staggerChildren, staggerItem, inkBleed } from '../motion/variants';

/**
 * Today — the open page of Abby's journal, dated today.
 *
 * Surfaces the full RPG loop as the first thing she sees:
 *   - Adventurer vitals (pet, sigil, streak)
 *   - Active timer rune band (if clocked in)
 *   - Today's Quests (chores + homework + milestones + trial + habits)
 *   - Recent Loot (drops)
 *   - Treasury strip (balance/coins/hours/earned)
 *   - Active ventures
 *   - Savings goals
 *   - Recent Badges
 */
export default function Dashboard() {
  const { data, loading, error, reload } = useApi(getDashboard);
  const { data: recentDrops } = useApi(getRecentDrops);
  const { data: stableData } = useApi(getStable);
  const { data: activeQuest } = useApi(getActiveQuest);
  const { user } = useAuth();
  const navigate = useNavigate();

  if (loading) return <Loader />;
  if (error || !data) {
    return (
      <div className="max-w-6xl mx-auto space-y-3">
        <ErrorAlert message={error || 'Could not load today’s entry.'} />
        <button
          type="button"
          onClick={reload}
          className="px-4 py-2 text-sm bg-sheikah-teal-deep text-ink-page-rune-glow rounded-lg hover:bg-sheikah-teal transition-colors font-display"
        >
          Try again
        </button>
      </div>
    );
  }

  const {
    active_timer, current_balance, coin_balance, this_week, active_projects,
    recent_badges, streak_days, savings_goals, chores_today,
    pending_chore_approvals, rpg,
  } = data;

  const activePet = stableData?.pets?.find((p) => p.is_active) || null;
  const activeMount = stableData?.mounts?.find((m) => m.is_active) || null;
  const isParent = user?.role === 'parent';

  // Build a unified "Today's Quests" list from chores + trial + habits + homework.
  const todayQuests = buildTodayQuests({ chores_today, activeQuest, rpg, activeTimer: active_timer });

  const streakMultiplier = rpg?.login_streak
    ? Math.min(1 + rpg.login_streak * 0.07, 2).toFixed(2)
    : null;

  const today = new Date();
  const weekday = today.toLocaleDateString(undefined, { weekday: 'long' });
  const dateStr = today.toLocaleDateString(undefined, { month: 'long', day: 'numeric' });

  return (
    <motion.div variants={inkBleed} initial="initial" animate="animate" className="max-w-6xl mx-auto space-y-6">
      {/* Date header */}
      <header>
        <div className="font-script text-sheikah-teal-deep text-base md:text-lg">
          {weekday} · {dateStr}
        </div>
        <h1 className="font-display italic text-3xl md:text-5xl text-ink-primary leading-tight">
          Today&apos;s Entry
        </h1>
      </header>

      {/* Active timer rune band */}
      {active_timer && (
        <RuneBand
          projectTitle={active_timer.project_title}
          elapsedLabel={formatDuration(active_timer.elapsed_minutes)}
          onClick={() => navigate('/clock')}
        />
      )}

      {/* Adventurer vitals strip — pet · sigil · streak */}
      <motion.div
        variants={staggerChildren}
        initial="initial"
        animate="animate"
        className="grid md:grid-cols-3 gap-3"
      >
        <motion.div variants={staggerItem}>
          {activePet ? (
            <div onClick={() => navigate('/bestiary?tab=party')} className="cursor-pointer h-full">
              <PartyCard
                pet={{
                  species_name: activePet.species?.name,
                  potion_variant: activePet.potion?.name,
                  growth_points: activePet.growth_points,
                  art_url: activePet.species?.icon_url,
                }}
                mount={activeMount ? { species_name: activeMount.species?.name } : null}
                variant="compact"
              />
            </div>
          ) : (
            <ParchmentCard className="h-full flex flex-col items-center justify-center text-center py-4">
              <EggIcon size={28} className="text-ink-whisper mb-1" />
              <div className="font-script text-ink-secondary text-sm">No companion yet</div>
              <button
                type="button"
                onClick={() => navigate('/bestiary?tab=satchel')}
                className="font-body text-xs text-sheikah-teal-deep hover:underline mt-1"
              >
                Find an egg →
              </button>
            </ParchmentCard>
          )}
        </motion.div>

        <motion.div variants={staggerItem}>
          <ParchmentCard
            tone="bright"
            className="h-full cursor-pointer"
            onClick={() => navigate('/sigil')}
          >
            <div className="flex items-center gap-3">
              <div className="w-14 h-14 rounded-full bg-sheikah-teal/15 border-2 border-sheikah-teal/50 flex items-center justify-center shrink-0">
                <span className="font-display text-xl text-sheikah-teal-deep">
                  {(user?.display_name || user?.username || '?')[0].toUpperCase()}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="font-display text-lg leading-tight truncate">
                  {user?.display_name || user?.username}
                </div>
                <div className="font-script text-ink-whisper text-xs">
                  level {rpg?.level ?? 1} · {rpg?.xp_to_next ? `${rpg.xp_to_next} XP to next` : 'adventurer'}
                </div>
                {rpg?.xp_percent != null && (
                  <div className="h-1 bg-ink-page-shadow/60 rounded-full mt-1.5 overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal rounded-full"
                      style={{ width: `${rpg.xp_percent}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          </ParchmentCard>
        </motion.div>

        <motion.div variants={staggerItem}>
          <ParchmentCard tone="bright" className="h-full">
            <StreakFlame
              streak={rpg?.login_streak ?? streak_days ?? 0}
              longest={rpg?.longest_login_streak ?? 0}
              multiplier={streakMultiplier}
            />
            {rpg?.perfect_days_count > 0 && (
              <div className="mt-2 pt-2 border-t border-ink-page-shadow/60 flex items-center gap-1.5">
                <Sparkles size={14} className="text-gold-leaf" />
                <span className="font-script text-xs text-ink-secondary">
                  {rpg.perfect_days_count} perfect {rpg.perfect_days_count === 1 ? 'day' : 'days'} logged
                </span>
              </div>
            )}
          </ParchmentCard>
        </motion.div>
      </motion.div>

      {/* Parent approval prompt */}
      {isParent && pending_chore_approvals > 0 && (
        <ParchmentCard
          tone="bright"
          className="border-ember/60 bg-ember/10 cursor-pointer"
          onClick={() => navigate('/quests?tab=rituals')}
        >
          <div className="flex items-center gap-3">
            <ClipboardCheck size={22} className="text-ember-deep" />
            <div className="flex-1">
              <div className="font-display text-base text-ink-primary">
                {pending_chore_approvals} ritual{pending_chore_approvals !== 1 ? 's' : ''} awaiting your seal
              </div>
              <div className="font-script text-xs text-ink-whisper">
                Tap to review and approve
              </div>
            </div>
            <RuneBadge tone="ember">pending</RuneBadge>
          </div>
        </ParchmentCard>
      )}

      {/* Today's Quests — unified log */}
      {todayQuests.length > 0 && (
        <section>
          <SectionHeader
            title="Today's Quests"
            kicker="to be inked before nightfall"
            count={todayQuests.length}
          />
          <ParchmentCard flourish>
            <ul className="space-y-2">
              {todayQuests.map((q) => (
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
          </ParchmentCard>
        </section>
      )}

      {/* Recent Loot */}
      {recentDrops?.length > 0 && (
        <section>
          <SectionHeader title="Recent Loot" kicker="drops from the last two days" />
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

      {/* Treasury strip */}
      <section>
        <SectionHeader title="Treasury" kicker="this week at a glance" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <TreasuryStat
            label="Balance"
            value={formatCurrency(current_balance)}
            tone="moss"
            onClick={() => navigate('/treasury?tab=coffers')}
          />
          <TreasuryStat
            label="Coins"
            value={coin_balance ?? 0}
            icon={<CoinIcon size={18} />}
            tone="gold"
            onClick={() => navigate('/treasury?tab=bazaar')}
          />
          <TreasuryStat
            label="Hours this week"
            value={`${this_week?.hours_worked ?? 0}h`}
            tone="teal"
            onClick={() => navigate('/treasury?tab=wages')}
          />
          <TreasuryStat
            label="Earned this week"
            value={formatCurrency(this_week?.earnings)}
            tone="ember"
          />
        </div>
      </section>

      {/* Active ventures */}
      {active_projects?.length > 0 && (
        <section>
          <SectionHeader title="Next Up" kicker="ventures under way" />
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {active_projects.map((p) => (
              <motion.div
                key={p.id}
                whileHover={{ y: -2 }}
                onClick={() => navigate(`/quests/ventures/${p.id}`)}
                className="cursor-pointer"
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
                        <span>
                          {p.milestones_completed}/{p.milestones_total}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                          style={{
                            width: `${(p.milestones_completed / p.milestones_total) * 100}%`,
                          }}
                        />
                      </div>
                    </>
                  )}
                </ParchmentCard>
              </motion.div>
            ))}
          </div>
        </section>
      )}

      {/* Savings goals */}
      {savings_goals?.length > 0 && (
        <section>
          <SectionHeader title="Hoard" kicker="treasure chests in progress" />
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
                <div className="font-script text-xs text-ink-whisper text-right mt-1">
                  {goal.percent_complete}%
                </div>
              </ParchmentCard>
            ))}
          </div>
        </section>
      )}

      {/* Recent Badges */}
      {recent_badges?.length > 0 && (
        <section>
          <DeckleDivider glyph="flourish-corner" label="recent accolades" />
          <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
            {recent_badges.map((b, i) => (
              <motion.button
                key={i}
                type="button"
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.08 }}
                onClick={() => navigate('/atlas?tab=skills')}
                className="shrink-0 w-28 text-center p-3 rounded-xl bg-ink-page-aged border border-ink-page-shadow hover:border-gold-leaf/60 transition-colors"
              >
                <div className="text-4xl mb-1">{b.badge__icon || '🏅'}</div>
                <div className="font-body text-xs font-medium truncate">{b.badge__name}</div>
              </motion.button>
            ))}
          </div>
        </section>
      )}
    </motion.div>
  );
}

/* ─── helpers ────────────────────────────────────────────────────── */

function SectionHeader({ title, kicker, count }) {
  return (
    <div className="mb-3 flex items-end gap-3">
      <div>
        {kicker && (
          <div className="font-script text-sheikah-teal-deep text-sm">{kicker}</div>
        )}
        <h2 className="font-display text-xl md:text-2xl text-ink-primary leading-tight">
          {title}
        </h2>
      </div>
      {count != null && (
        <RuneBadge tone="teal" className="mb-1">
          {count}
        </RuneBadge>
      )}
    </div>
  );
}

function TreasuryStat({ label, value, icon, tone = 'teal', onClick }) {
  const tones = {
    moss: 'text-moss',
    gold: 'text-gold-leaf',
    teal: 'text-sheikah-teal-deep',
    ember: 'text-ember-deep',
  };
  const Component = onClick ? 'button' : 'div';
  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={`${onClick ? 'cursor-pointer hover:bg-ink-page-rune-glow/80 transition-colors' : ''} text-left rounded-xl border border-ink-page-shadow bg-ink-page-aged p-3`}
    >
      <div className={`flex items-center gap-1 mb-0.5 ${tones[tone]}`}>
        {icon}
        <span className="font-script text-xs uppercase tracking-wider">{label}</span>
      </div>
      <div className="font-display text-xl md:text-2xl font-semibold text-ink-primary">
        {value}
      </div>
    </Component>
  );
}

function buildTodayQuests({ chores_today, activeQuest, rpg, activeTimer }) {
  const out = [];

  // Active project milestone teaser (if clocked in on a project)
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

  // Active RPG trial
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

  // Today's chores
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
    });
  });

  // Habits (positive taps surfaced as quests; tap count shown in meta)
  (rpg?.habits_today || []).slice(0, 5).forEach((h) => {
    out.push({
      id: `habit-${h.id}`,
      title: h.name,
      meta: `habit · strength ${h.strength ?? 0} · ${h.taps_today}× today`,
      status: 'pending',
      kind: 'virtue',
      tone: 'gold',
      icon: h.icon ? <span className="text-base">{h.icon}</span> : <ScrollIcon size={16} />,
    });
  });

  return out;
}

function mapProjectTone(status) {
  switch (status) {
    case 'completed':  return 'moss';
    case 'in_review':  return 'royal';
    case 'in_progress': return 'ember';
    case 'active':     return 'teal';
    case 'archived':
    case 'draft':      return 'ink';
    default: return 'teal';
  }
}

import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Check, ClipboardCheck, Clock, Coins, DollarSign, Flame, FolderKanban, Trophy, Timer, Target } from 'lucide-react';
import { getDashboard } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import DifficultyStars from '../components/DifficultyStars';
import Loader from '../components/Loader';
import ProgressBar from '../components/ProgressBar';
import StatusBadge from '../components/StatusBadge';
import { formatCurrency, formatDuration } from '../utils/format';

export default function Dashboard() {
  const { data, loading } = useApi(getDashboard);
  const navigate = useNavigate();

  if (loading) return <Loader />;
  if (!data) return null;

  const { active_timer, current_balance, coin_balance, this_week, active_projects, recent_badges, streak_days, savings_goals, chores_today, pending_chore_approvals } = data;

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold text-forge-text">Dashboard</h1>

      {/* Active Timer Hero */}
      {active_timer && (
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="cursor-pointer"
          onClick={() => navigate('/clock')}
        >
          <Card className="border-amber-primary/50 bg-amber-primary/5">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-amber-primary/20 rounded-full flex items-center justify-center">
                <Timer className="text-amber-highlight animate-pulse" size={24} />
              </div>
              <div className="flex-1">
                <div className="text-sm text-amber-highlight font-medium">Currently Working</div>
                <div className="text-lg font-heading font-bold">{active_timer.project_title}</div>
              </div>
              <div className="font-heading text-2xl text-amber-highlight font-bold">
                {formatDuration(active_timer.elapsed_minutes)}
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.05 }}>
          <Card>
            <DollarSign className="text-green-400 mb-1" size={20} />
            <div className="font-heading text-2xl font-bold">{formatCurrency(current_balance)}</div>
            <div className="text-xs text-forge-text-dim">Balance</div>
          </Card>
        </motion.div>
        <motion.div
          initial={{ y: 10, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          transition={{ delay: 0.08 }}
          className="cursor-pointer"
          onClick={() => navigate('/rewards')}
        >
          <Card>
            <Coins className="text-amber-highlight mb-1" size={20} />
            <div className="font-heading text-2xl font-bold">{coin_balance ?? 0}</div>
            <div className="text-xs text-forge-text-dim">Coins</div>
          </Card>
        </motion.div>
        <motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 }}>
          <Card>
            <Clock className="text-blue-400 mb-1" size={20} />
            <div className="font-heading text-2xl font-bold">{this_week?.hours_worked}h</div>
            <div className="text-xs text-forge-text-dim">This Week</div>
          </Card>
        </motion.div>
        <motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.15 }}>
          <Card>
            <DollarSign className="text-amber-highlight mb-1" size={20} />
            <div className="font-heading text-2xl font-bold">{formatCurrency(this_week?.earnings)}</div>
            <div className="text-xs text-forge-text-dim">Earned This Week</div>
          </Card>
        </motion.div>
        <motion.div initial={{ y: 10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.2 }}>
          <Card>
            <Flame className="text-orange-400 mb-1" size={20} />
            <div className="font-heading text-2xl font-bold">{streak_days}</div>
            <div className="text-xs text-forge-text-dim">Day Streak</div>
          </Card>
        </motion.div>
      </div>

      {/* Today's Chores */}
      {chores_today?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2 cursor-pointer" onClick={() => navigate('/chores')}>
            <ClipboardCheck size={18} /> Today&apos;s Chores
          </h2>
          <div className="space-y-1.5">
            {chores_today.map((c) => (
              <Card key={c.id} className={`flex items-center gap-3 py-2 ${c.is_done ? 'opacity-50' : ''}`} onClick={() => navigate('/chores')}>
                <span className="text-lg shrink-0">{c.icon || '📋'}</span>
                <span className={`text-sm flex-1 ${c.is_done ? 'line-through text-forge-text-dim' : 'font-medium'}`}>{c.title}</span>
                {c.is_done ? (
                  <Check size={16} className="text-green-400 shrink-0" />
                ) : (
                  <span className="text-xs text-forge-text-dim shrink-0">${c.reward_amount}</span>
                )}
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Parent: pending chore approvals */}
      {pending_chore_approvals > 0 && (
        <motion.div
          initial={{ scale: 0.95, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="cursor-pointer"
          onClick={() => navigate('/chores')}
        >
          <Card className="border-yellow-500/30 bg-yellow-500/5">
            <div className="flex items-center gap-3">
              <ClipboardCheck size={20} className="text-yellow-400" />
              <div className="flex-1">
                <div className="text-sm font-medium">{pending_chore_approvals} chore{pending_chore_approvals !== 1 ? 's' : ''} awaiting approval</div>
              </div>
            </div>
          </Card>
        </motion.div>
      )}

      {/* Active Projects */}
      {active_projects?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <FolderKanban size={18} /> Active Projects
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {active_projects.map((p) => (
              <motion.div
                key={p.id}
                whileHover={{ y: -2 }}
                className="cursor-pointer"
                onClick={() => navigate(`/projects/${p.id}`)}
              >
                <Card>
                  <div className="flex items-start justify-between mb-2">
                    <div className="font-semibold truncate">{p.title}</div>
                    <StatusBadge status={p.status} />
                  </div>
                  <div className="flex items-center gap-2 text-xs text-forge-text-dim mb-2">
                    <DifficultyStars difficulty={p.difficulty} />
                  </div>
                  {p.milestones_total > 0 && (
                    <div>
                      <div className="flex justify-between text-xs text-forge-text-dim mb-1">
                        <span>Milestones</span>
                        <span>{p.milestones_completed}/{p.milestones_total}</span>
                      </div>
                      <ProgressBar value={p.milestones_completed} max={p.milestones_total} />
                    </div>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      )}

      {/* Savings Goals */}
      {savings_goals?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <Target size={18} /> Savings Goals
          </h2>
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3">
            {savings_goals.map((goal) => (
              <Card key={goal.id}>
                <div className="flex items-center gap-2 mb-2">
                  {goal.icon && <span className="text-xl">{goal.icon}</span>}
                  <span className="font-medium text-sm">{goal.title}</span>
                </div>
                <div className="flex justify-between text-xs text-forge-text-dim mb-1">
                  <span>{formatCurrency(goal.current_amount)}</span>
                  <span>{formatCurrency(goal.target_amount)}</span>
                </div>
                <ProgressBar value={goal.percent_complete} max={100} color="bg-green-500" className="h-2" />
                <div className="text-xs text-forge-text-dim mt-1 text-right">{goal.percent_complete}%</div>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Recent Badges */}
      {recent_badges?.length > 0 && (
        <div>
          <h2 className="font-heading text-lg font-bold mb-3 flex items-center gap-2">
            <Trophy size={18} /> Recent Badges
          </h2>
          <div className="flex gap-3 overflow-x-auto pb-2">
            {recent_badges.map((b, i) => (
              <motion.div
                key={i}
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ delay: i * 0.1 }}
              >
                <Card className="shrink-0 text-center w-24">
                  <div className="text-3xl mb-1">{b.badge__icon}</div>
                  <div className="text-xs font-medium truncate">{b.badge__name}</div>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

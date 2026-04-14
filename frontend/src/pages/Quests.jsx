import { useState } from 'react';
import { motion } from 'framer-motion';
import { Swords, Play, Shield } from 'lucide-react';
import {
  getActiveQuest, getAvailableQuests, startQuest, getQuestHistory,
} from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import ProgressBar from '../components/ProgressBar';
import TabButton from '../components/TabButton';
import { normalizeList } from '../utils/api';
import { formatDate } from '../utils/format';
import { STATUS_COLORS } from '../constants/colors';

export default function Quests() {
  const { data: activeQuest, loading: loadingActive, reload: reloadActive } = useApi(getActiveQuest);
  const { data: availableData, loading: loadingAvailable } = useApi(getAvailableQuests);
  const { data: historyData, loading: loadingHistory } = useApi(getQuestHistory);
  const [tab, setTab] = useState('current');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(null);

  const loading = loadingActive || loadingAvailable || loadingHistory;
  if (loading) return <Loader />;

  const available = normalizeList(availableData);
  const history = normalizeList(historyData);

  const handleStart = async (defId) => {
    setStarting(defId);
    setError('');
    try {
      await startQuest(defId);
      reloadActive();
    } catch (e) { setError(e.message); }
    finally { setStarting(null); }
  };

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold flex items-center gap-2">
        <Swords size={22} /> Quests
      </h1>

      <ErrorAlert message={error} />

      {/* Tabs */}
      <div className="flex gap-2">
        <TabButton active={tab === 'current'} onClick={() => setTab('current')}>Current</TabButton>
        <TabButton active={tab === 'available'} onClick={() => setTab('available')}>Available ({available.length})</TabButton>
        <TabButton active={tab === 'history'} onClick={() => setTab('history')}>History</TabButton>
      </div>

      {/* Current Quest */}
      {tab === 'current' && (
        activeQuest ? (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <Card className="space-y-4">
              <div className="flex items-start gap-3">
                <div className="text-4xl">{activeQuest.definition.icon}</div>
                <div className="flex-1">
                  <div className="font-heading font-bold text-lg">{activeQuest.definition.name}</div>
                  <div className="text-sm text-forge-text-dim">{activeQuest.definition.description}</div>
                  <div className="flex items-center gap-2 mt-1 text-xs text-forge-text-dim">
                    <span className={`px-1.5 py-0.5 rounded-full ${STATUS_COLORS[activeQuest.status]}`}>
                      {activeQuest.status}
                    </span>
                    <span>{activeQuest.definition.quest_type_display}</span>
                  </div>
                </div>
              </div>

              {/* Progress */}
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="font-medium">
                    {activeQuest.definition.quest_type === 'boss' ? 'Damage Dealt' : 'Collected'}
                  </span>
                  <span className="text-forge-text-dim">
                    {activeQuest.current_progress} / {activeQuest.effective_target}
                  </span>
                </div>
                <ProgressBar
                  value={activeQuest.current_progress}
                  max={activeQuest.effective_target}
                  color={activeQuest.definition.quest_type === 'boss' ? 'bg-red-500' : 'bg-blue-500'}
                />
                <div className="text-xs text-forge-text-dim mt-1">
                  {activeQuest.progress_percent}% complete
                </div>
              </div>

              {/* Rage shield indicator */}
              {activeQuest.rage_shield > 0 && (
                <div className="flex items-center gap-2 text-xs text-orange-400">
                  <Shield size={14} />
                  <span>Boss raged! +{activeQuest.rage_shield} shield</span>
                </div>
              )}

              {/* Rewards preview */}
              <div className="text-xs text-forge-text-dim">
                <span className="font-medium">Rewards: </span>
                {activeQuest.definition.coin_reward > 0 && <span>{activeQuest.definition.coin_reward} coins </span>}
                {activeQuest.definition.xp_reward > 0 && <span>{activeQuest.definition.xp_reward} XP </span>}
                {activeQuest.definition.reward_items?.map(r => (
                  <span key={r.id}>{r.item_icon} {r.item_name} x{r.quantity} </span>
                ))}
              </div>

              {/* Time remaining */}
              <div className="text-xs text-forge-text-dim">
                Ends: {formatDate(activeQuest.end_date)}
              </div>
            </Card>
          </motion.div>
        ) : (
          <EmptyState>No active quest. Start one from the Available tab!</EmptyState>
        )
      )}

      {/* Available Quests */}
      {tab === 'available' && (
        available.length === 0 ? (
          <EmptyState>No quests available right now.</EmptyState>
        ) : (
          <div className="space-y-3">
            {available.map((qd) => (
              <Card key={qd.id} className="flex items-center gap-4">
                <div className="text-3xl shrink-0">{qd.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{qd.name}</div>
                  <div className="text-xs text-forge-text-dim truncate">{qd.description}</div>
                  <div className="flex gap-2 mt-1 text-[10px] text-forge-text-dim">
                    <span>{qd.quest_type_display}</span>
                    <span>Target: {qd.target_value}</span>
                    <span>{qd.duration_days}d</span>
                    {qd.coin_reward > 0 && <span>{qd.coin_reward} coins</span>}
                  </div>
                </div>
                {!activeQuest && (
                  <button
                    onClick={() => handleStart(qd.id)}
                    disabled={starting === qd.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-amber-primary text-white text-xs font-medium shrink-0"
                  >
                    <Play size={12} /> {starting === qd.id ? 'Starting...' : 'Start'}
                  </button>
                )}
              </Card>
            ))}
          </div>
        )
      )}

      {/* History */}
      {tab === 'history' && (
        history.length === 0 ? (
          <EmptyState>No quest history yet.</EmptyState>
        ) : (
          <div className="space-y-2">
            {history.map((q) => (
              <Card key={q.id} className="flex items-center gap-3">
                <div className="text-2xl shrink-0">{q.definition.icon}</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium">{q.definition.name}</div>
                  <div className="text-xs text-forge-text-dim">
                    {q.current_progress}/{q.definition.target_value}
                  </div>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_COLORS[q.status]}`}>
                  {q.status}
                </span>
              </Card>
            ))}
          </div>
        )
      )}
    </div>
  );
}

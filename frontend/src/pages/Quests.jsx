import { useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { Play, Shield } from 'lucide-react';
import {
  getActiveQuest, getAvailableQuests, startQuest, getQuestHistory, getFamilyQuests,
} from '../api';
import { useApi } from '../hooks/useApi';
import { useRole } from '../hooks/useRole';
import Loader from '../components/Loader';
import EmptyState from '../components/EmptyState';
import ErrorAlert from '../components/ErrorAlert';
import TabButton from '../components/TabButton';
import ParchmentCard from '../components/journal/ParchmentCard';
import RuneBadge from '../components/journal/RuneBadge';
import { DragonIcon } from '../components/icons/JournalIcons';
import RpgSprite from '../components/rpg/RpgSprite';
import { normalizeList } from '../utils/api';
import { formatDate } from '../utils/format';
import { buttonPrimary } from '../constants/styles';

const STATUS_TONE = {
  active: 'teal',
  completed: 'moss',
  expired: 'ink',
  failed: 'ember',
};

export default function Quests() {
  const { isParent } = useRole();
  const { data: activeQuest, loading: loadingActive, reload: reloadActive } = useApi(getActiveQuest);
  const { data: availableData, loading: loadingAvailable } = useApi(getAvailableQuests);
  const { data: historyData, loading: loadingHistory } = useApi(getQuestHistory);
  const fetchFamily = useCallback(
    () => (isParent ? getFamilyQuests() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: familyData, loading: loadingFamily } = useApi(fetchFamily, [isParent]);
  const [tab, setTab] = useState('current');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(null);

  const loading = loadingActive || loadingAvailable || loadingHistory || loadingFamily;
  if (loading) return <Loader />;

  const available = normalizeList(availableData);
  const history = normalizeList(historyData);
  const familyRows = (familyData?.results || []).filter((row) => row.quest);

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
      <header>
        <div className="font-script text-sheikah-teal-deep text-base">
          trials · epic campaigns & collection hunts
        </div>
        <h2 className="font-display italic text-2xl md:text-3xl text-ink-primary leading-tight">
          Trials
        </h2>
      </header>

      <ErrorAlert message={error} />

      {/* Parent-only family roll-up */}
      {isParent && familyRows.length > 0 && (
        <ParchmentCard className="space-y-3">
          <div className="font-display text-lg text-ink-primary leading-tight">Family Trials</div>
          <div className="space-y-2">
            {familyRows.map((row) => (
              <div key={row.child_id} className="flex items-center gap-3">
                <div className="font-script text-sm text-ink-primary w-28 shrink-0 truncate">
                  {row.child_name}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline gap-2">
                    <span className="font-body text-sm text-ink-secondary truncate">
                      {row.quest.definition.name}
                    </span>
                    <span className="font-rune text-xs text-ink-whisper tabular-nums shrink-0">
                      {row.quest.current_progress}/{row.quest.effective_target}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal"
                      style={{ width: `${row.quest.progress_percent}%` }}
                    />
                  </div>
                </div>
                <div className="font-rune text-xs text-ink-whisper tabular-nums shrink-0 w-20 text-right">
                  ends {formatDate(row.quest.end_date)}
                </div>
              </div>
            ))}
          </div>
        </ParchmentCard>
      )}

      <div className="flex gap-2 flex-wrap">
        <TabButton active={tab === 'current'} onClick={() => setTab('current')}>Current</TabButton>
        <TabButton active={tab === 'available'} onClick={() => setTab('available')}>
          Available ({available.length})
        </TabButton>
        <TabButton active={tab === 'history'} onClick={() => setTab('history')}>History</TabButton>
      </div>

      {/* Current Trial */}
      {tab === 'current' && (
        activeQuest ? (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
            <ParchmentCard flourish className="space-y-4">
              <div className="flex items-start gap-3">
                <RpgSprite
                  spriteKey={activeQuest.definition.sprite_key}
                  icon={activeQuest.definition.icon}
                  size={56}
                  alt={activeQuest.definition.name}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-display text-2xl text-ink-primary leading-tight">
                    {activeQuest.definition.name}
                  </div>
                  <div className="font-body text-sm text-ink-secondary">
                    {activeQuest.definition.description}
                  </div>
                  <div className="flex items-center gap-2 mt-2 flex-wrap">
                    <RuneBadge tone={STATUS_TONE[activeQuest.status] || 'teal'} size="sm">
                      {activeQuest.status}
                    </RuneBadge>
                    <RuneBadge tone="royal" size="sm">
                      {activeQuest.definition.quest_type_display}
                    </RuneBadge>
                  </div>
                </div>
              </div>

              {/* Progress */}
              <div>
                <div className="flex justify-between font-script text-sm mb-1">
                  <span className="text-ink-primary">
                    {activeQuest.definition.quest_type === 'boss' ? 'Damage dealt' : 'Collected'}
                  </span>
                  <span className="text-ink-whisper font-rune tabular-nums">
                    {activeQuest.current_progress} / {activeQuest.effective_target}
                  </span>
                </div>
                <div className="h-3 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                  <div
                    className={`h-full rounded-full ${
                      activeQuest.definition.quest_type === 'boss'
                        ? 'bg-gradient-to-r from-ember-deep to-ember'
                        : 'bg-gradient-to-r from-sheikah-teal-deep to-sheikah-teal'
                    }`}
                    style={{ width: `${activeQuest.progress_percent}%` }}
                  />
                </div>
                <div className="font-rune text-xs text-ink-whisper mt-1">
                  {activeQuest.progress_percent}% complete
                </div>
              </div>

              {/* Party contributions — only render when it adds signal */}
              {activeQuest.participants?.length > 1 && (
                <div>
                  <div className="font-script text-sm text-ink-primary mb-1">Party</div>
                  <div className="space-y-1">
                    {activeQuest.participants.map((p) => {
                      const pct = activeQuest.current_progress > 0
                        ? Math.round((p.contribution / activeQuest.current_progress) * 100)
                        : 0;
                      return (
                        <div key={p.id} className="flex items-center gap-2">
                          <span className="font-script text-xs text-ink-secondary w-20 shrink-0 truncate">
                            {p.user_name}
                          </span>
                          <div className="flex-1 h-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-moss-deep to-moss"
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                          <span className="font-rune text-xs text-ink-whisper tabular-nums w-16 text-right shrink-0">
                            {p.contribution} ({pct}%)
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Rage shield */}
              {activeQuest.rage_shield > 0 && (
                <div className="flex items-center gap-2 font-script text-sm text-ember-deep bg-ember/10 rounded-lg p-2 border border-ember/40">
                  <Shield size={14} /> Boss raged! +{activeQuest.rage_shield} shield
                </div>
              )}

              {/* Rewards preview */}
              <div className="font-script text-sm text-ink-secondary">
                <span className="text-ink-whisper uppercase tracking-wider text-xs">rewards · </span>
                {activeQuest.definition.coin_reward > 0 && (
                  <span className="mr-2">{activeQuest.definition.coin_reward} coins</span>
                )}
                {activeQuest.definition.xp_reward > 0 && (
                  <span className="mr-2">{activeQuest.definition.xp_reward} XP</span>
                )}
                {activeQuest.definition.reward_items?.map((r) => (
                  <span key={r.id} className="mr-2 inline-flex items-center gap-1 align-middle">
                    <RpgSprite
                      spriteKey={r.item_sprite_key}
                      icon={r.item_icon}
                      size={24}
                      alt={r.item_name}
                    />
                    {r.item_name} ×{r.quantity}
                  </span>
                ))}
              </div>

              <div className="font-script text-xs text-ink-whisper italic">
                Ends: {formatDate(activeQuest.end_date)}
              </div>
            </ParchmentCard>
          </motion.div>
        ) : (
          <EmptyState icon={<DragonIcon size={32} />}>
            No trial under way. Choose one from the Available list to begin the hunt.
          </EmptyState>
        )
      )}

      {/* Available Trials */}
      {tab === 'available' && (
        available.length === 0 ? (
          <EmptyState icon={<DragonIcon size={32} />}>
            No trials posted on the board right now.
          </EmptyState>
        ) : (
          <div className="space-y-3">
            {available.map((qd) => (
              <ParchmentCard key={qd.id} className="flex items-center gap-4">
                <div className="shrink-0">
                  <RpgSprite
                    spriteKey={qd.sprite_key}
                    icon={qd.icon}
                    size={48}
                    alt={qd.name}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-display text-base text-ink-primary leading-tight">
                    {qd.name}
                  </div>
                  <div className="font-body text-xs text-ink-secondary truncate">
                    {qd.description}
                  </div>
                  <div className="flex gap-2 mt-1 font-script text-xs text-ink-whisper flex-wrap">
                    <span>{qd.quest_type_display}</span>
                    <span>target: {qd.target_value}</span>
                    <span>{qd.duration_days}d</span>
                    {qd.coin_reward > 0 && <span>{qd.coin_reward} coins</span>}
                  </div>
                </div>
                {!activeQuest && (
                  <button
                    type="button"
                    onClick={() => handleStart(qd.id)}
                    disabled={starting === qd.id}
                    className={`${buttonPrimary} flex items-center gap-1 px-3 py-1.5 text-xs shrink-0`}
                  >
                    <Play size={12} /> {starting === qd.id ? 'Starting…' : 'Begin'}
                  </button>
                )}
              </ParchmentCard>
            ))}
          </div>
        )
      )}

      {/* History */}
      {tab === 'history' && (
        history.length === 0 ? (
          <EmptyState>No trials in the chronicle yet.</EmptyState>
        ) : (
          <div className="space-y-2">
            {history.map((q) => (
              <ParchmentCard key={q.id} className="flex items-center gap-3">
                <div className="shrink-0">
                  <RpgSprite
                    spriteKey={q.definition.sprite_key}
                    icon={q.definition.icon}
                    size={40}
                    alt={q.definition.name}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-body text-sm font-medium text-ink-primary">
                    {q.definition.name}
                  </div>
                  <div className="font-rune text-xs text-ink-whisper tabular-nums">
                    {q.current_progress}/{q.definition.target_value}
                  </div>
                </div>
                <RuneBadge tone={STATUS_TONE[q.status] || 'ink'} size="sm">
                  {q.status}
                </RuneBadge>
              </ParchmentCard>
            ))}
          </div>
        )
      )}
    </div>
  );
}

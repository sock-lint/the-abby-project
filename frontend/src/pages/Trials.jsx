import { useCallback, useState } from 'react';
import { motion } from 'framer-motion';
import { Play, Shield, Sword, X } from 'lucide-react';
import {
  getActiveQuest, getAvailableQuests, startQuest, getQuestHistory, getFamilyQuests,
  getChildren, createQuest,
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
import Button from '../components/Button';
import { TextField, TextAreaField, SelectField } from '../components/form';

const STATUS_TONE = {
  active: 'teal',
  completed: 'moss',
  expired: 'ink',
  failed: 'ember',
};

const DEFAULT_CHALLENGE = {
  name: '',
  description: '',
  quest_type: 'collection',
  target_value: 5,
  duration_days: 7,
  coin_reward: 20,
  xp_reward: 40,
  assigned_to: '',
};

export default function Trials() {
  const { isParent } = useRole();
  const { data: activeQuest, loading: loadingActive, reload: reloadActive } = useApi(getActiveQuest);
  const { data: availableData, loading: loadingAvailable } = useApi(getAvailableQuests);
  const { data: historyData, loading: loadingHistory } = useApi(getQuestHistory);
  const fetchFamily = useCallback(
    () => (isParent ? getFamilyQuests() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: familyData, loading: loadingFamily, reload: reloadFamily } = useApi(fetchFamily, [isParent]);
  const fetchKids = useCallback(
    () => (isParent ? getChildren() : Promise.resolve({ results: [] })),
    [isParent],
  );
  const { data: childrenData } = useApi(fetchKids, [isParent]);
  const [tab, setTab] = useState('current');
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(null);
  const [showChallenge, setShowChallenge] = useState(false);
  const [challenge, setChallenge] = useState(DEFAULT_CHALLENGE);
  const [issuing, setIssuing] = useState(false);
  const children = normalizeList(childrenData);

  const loading = loadingActive || loadingAvailable || loadingHistory || loadingFamily;
  if (loading) return <Loader />;

  const handleIssueChallenge = async () => {
    if (!challenge.assigned_to || !challenge.name || !challenge.description) return;
    setIssuing(true);
    setError('');
    try {
      await createQuest({
        name: challenge.name,
        description: challenge.description,
        quest_type: challenge.quest_type,
        target_value: Number(challenge.target_value) || 1,
        duration_days: Math.min(30, Math.max(1, Number(challenge.duration_days) || 7)),
        coin_reward: Number(challenge.coin_reward) || 0,
        xp_reward: Number(challenge.xp_reward) || 0,
        assigned_to: Number(challenge.assigned_to),
      });
      setShowChallenge(false);
      setChallenge(DEFAULT_CHALLENGE);
      reloadFamily();
    } catch (e) { setError(e.message); }
    finally { setIssuing(false); }
  };

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
        <div className="font-script text-sm text-ink-whisper mt-1 max-w-xl">
          boss trials take damage from your work and study · collection trials count items earned · only one active at a time
        </div>
      </header>

      <ErrorAlert message={error} />

      {/* Parent-only issue-challenge button */}
      {isParent && children.length > 0 && (
        <div className="flex justify-end">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setShowChallenge(!showChallenge)}
            className="flex items-center gap-1.5"
          >
            <Sword size={14} /> Issue Challenge
          </Button>
        </div>
      )}

      {/* Parent-only issue-challenge modal */}
      {isParent && showChallenge && (
        <ParchmentCard flourish seal>
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="font-script text-xs text-ink-whisper uppercase tracking-widest">
                custom campaign
              </div>
              <h3 className="font-display text-lg text-ink-primary">Issue a Challenge</h3>
              <div className="text-tiny text-ink-whisper mt-1">
                Authors a one-off quest and auto-assigns it to the chosen child.
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowChallenge(false)}
              aria-label="Close"
              className="p-1 rounded-full hover:bg-ink-page-shadow/50 transition-colors"
            >
              <X size={16} className="text-ink-secondary" />
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <SelectField
              id="challenge-kid"
              label="Assign to"
              value={challenge.assigned_to}
              onChange={(e) => setChallenge({ ...challenge, assigned_to: e.target.value })}
            >
              <option value="">Select a child…</option>
              {children.map((c) => (
                <option key={c.id} value={c.id}>{c.display_label || c.username}</option>
              ))}
            </SelectField>
            <SelectField
              id="challenge-type"
              label="Type"
              value={challenge.quest_type}
              onChange={(e) => setChallenge({ ...challenge, quest_type: e.target.value })}
            >
              <option value="collection">Collection (count)</option>
              <option value="boss">Boss (damage)</option>
            </SelectField>
            <TextField
              id="challenge-name"
              label="Title"
              value={challenge.name}
              onChange={(e) => setChallenge({ ...challenge, name: e.target.value })}
              placeholder="e.g. Weekend Kitchen Rally"
            />
            <TextField
              id="challenge-target"
              label="Target value"
              type="number"
              min="1"
              value={challenge.target_value}
              onChange={(e) => setChallenge({ ...challenge, target_value: e.target.value })}
              helpText={challenge.quest_type === 'boss' ? 'HP to deal' : 'Items to collect'}
            />
            <TextField
              id="challenge-days"
              label="Duration (days)"
              type="number"
              min="1"
              max="30"
              value={challenge.duration_days}
              onChange={(e) => setChallenge({ ...challenge, duration_days: e.target.value })}
            />
            <div className="grid grid-cols-2 gap-2">
              <TextField
                id="challenge-coins"
                label="Coin reward"
                type="number"
                min="0"
                value={challenge.coin_reward}
                onChange={(e) => setChallenge({ ...challenge, coin_reward: e.target.value })}
              />
              <TextField
                id="challenge-xp"
                label="XP reward"
                type="number"
                min="0"
                value={challenge.xp_reward}
                onChange={(e) => setChallenge({ ...challenge, xp_reward: e.target.value })}
              />
            </div>
          </div>
          <TextAreaField
            id="challenge-description"
            label="Description"
            value={challenge.description}
            onChange={(e) => setChallenge({ ...challenge, description: e.target.value })}
            rows={3}
            className="mt-3"
          />
          <Button
            onClick={handleIssueChallenge}
            disabled={
              !challenge.assigned_to || !challenge.name ||
              !challenge.description || issuing
            }
            className="w-full mt-3"
          >
            {issuing ? 'Issuing…' : 'Issue the challenge'}
          </Button>
        </ParchmentCard>
      )}

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
                  <Button
                    size="sm"
                    onClick={() => handleStart(qd.id)}
                    disabled={starting === qd.id}
                    className="flex items-center gap-1 text-xs shrink-0"
                  >
                    <Play size={12} /> {starting === qd.id ? 'Starting…' : 'Begin'}
                  </Button>
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

import { useState } from 'react';
import { Sword, X } from 'lucide-react';
import { createQuest } from '../../api';
import SkillTagEditor from '../../components/SkillTagEditor';
import ParchmentCard from '../../components/journal/ParchmentCard';
import Button from '../../components/Button';
import IconButton from '../../components/IconButton';
import { TextField, TextAreaField, SelectField } from '../../components/form';

const DEFAULT_CHALLENGE = {
  name: '',
  description: '',
  quest_type: 'collection',
  target_value: 5,
  duration_days: 7,
  coin_reward: 20,
  xp_reward: 40,
  assigned_to: '',
  is_coop: false,
  coop_user_ids: [],
  skill_tags: [],
  allowed_triggers: [],
  on_time_only: false,
};

// Trigger options that make sense for parent-authored quests. Mirrors
// apps.rpg.constants.TriggerType but trims to the ones that produce
// readable damage/collection contributions on a custom campaign.
const TRIGGER_OPTIONS = [
  ['chore_complete', 'Duty completed'],
  ['homework_complete', 'Homework approved'],
  ['homework_created', 'Homework planned ahead'],
  ['habit_log', 'Ritual tap'],
  ['clock_out', 'Clock-out hour'],
  ['milestone_complete', 'Milestone hit'],
  ['project_complete', 'Project complete'],
  ['journal_entry', 'Journal entry'],
  ['creation_logged', 'Creation logged'],
  ['savings_goal_complete', 'Savings goal hit'],
];

/**
 * IssueChallengeForm — parent-only "Issue a Challenge" toggle button plus
 * the collapsible form modal. Extracted verbatim from the old
 * pages/Trials.jsx:202–429 with no visual changes — `components/README.md`
 * explicitly flags forms as "do not over-decorate."
 *
 * Props:
 *   - children: list of family children
 *   - skills: list of skills (for SkillTagEditor)
 *   - onIssued(): called after a successful POST so the parent can refresh
 *   - onError(message): bubble up errors so the page-level ErrorAlert can
 *     render them
 */
export default function IssueChallengeForm({ children = [], skills = [], onIssued, onError }) {
  const [show, setShow] = useState(false);
  const [challenge, setChallenge] = useState(DEFAULT_CHALLENGE);
  const [issuing, setIssuing] = useState(false);

  const toggleCoopChild = (id) => {
    setChallenge((prev) => {
      const ids = new Set(prev.coop_user_ids);
      const key = String(id);
      if (ids.has(key)) ids.delete(key);
      else ids.add(key);
      return { ...prev, coop_user_ids: [...ids] };
    });
  };

  const toggleAllowedTrigger = (slug) => {
    setChallenge((prev) => {
      const set = new Set(prev.allowed_triggers);
      if (set.has(slug)) set.delete(slug);
      else set.add(slug);
      return { ...prev, allowed_triggers: [...set] };
    });
  };

  const handleIssueChallenge = async () => {
    const assigneeReady = challenge.is_coop
      ? challenge.coop_user_ids.length >= 2
      : Boolean(challenge.assigned_to);
    if (!assigneeReady || !challenge.name || !challenge.description) return;
    setIssuing(true);
    onError?.('');
    try {
      const payload = {
        name: challenge.name,
        description: challenge.description,
        quest_type: challenge.quest_type,
        target_value: Number(challenge.target_value) || 1,
        duration_days: Math.min(30, Math.max(1, Number(challenge.duration_days) || 7)),
        coin_reward: Number(challenge.coin_reward) || 0,
        xp_reward: Number(challenge.xp_reward) || 0,
      };
      if (challenge.is_coop) {
        payload.coop_user_ids = challenge.coop_user_ids.map(Number);
      } else {
        payload.assigned_to = Number(challenge.assigned_to);
      }
      const tf = {};
      if (challenge.allowed_triggers.length > 0) {
        tf.allowed_triggers = challenge.allowed_triggers;
      }
      if (challenge.on_time_only) tf.on_time = true;
      if (Object.keys(tf).length > 0) payload.trigger_filter = tf;
      if (challenge.skill_tags.length > 0) {
        payload.skill_tags = challenge.skill_tags;
      }
      await createQuest(payload);
      setShow(false);
      setChallenge(DEFAULT_CHALLENGE);
      onIssued?.();
    } catch (e) {
      onError?.(e.message);
    } finally {
      setIssuing(false);
    }
  };

  if (children.length === 0) return null;

  return (
    <div className="space-y-3">
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="secondary"
          onClick={() => setShow(!show)}
          className="flex items-center gap-1.5"
        >
          <Sword size={14} /> Issue Challenge
        </Button>
      </div>

      {show && (
        <ParchmentCard flourish seal>
          <div className="flex items-start justify-between mb-3">
            <div>
              <div className="font-script text-caption text-ink-whisper uppercase tracking-widest">
                custom campaign
              </div>
              <h3 className="font-display text-lg text-ink-primary">Issue a Challenge</h3>
              <div className="text-tiny text-ink-whisper mt-1">
                Authors a one-off quest and auto-assigns it to the chosen child.
              </div>
            </div>
            <IconButton
              onClick={() => setShow(false)}
              aria-label="Close"
              size="sm"
            >
              <X size={16} className="text-ink-secondary" />
            </IconButton>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {challenge.is_coop ? (
              <div className="md:col-span-1">
                <div className="font-script text-caption text-ink-whisper uppercase tracking-wider mb-1">
                  Co-op participants
                </div>
                <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto rounded-lg border border-ink-page-shadow bg-ink-page p-2">
                  {children.map((c) => {
                    const checked = challenge.coop_user_ids.includes(String(c.id));
                    return (
                      <label
                        key={c.id}
                        className={`flex items-center gap-1.5 px-2 py-1 rounded-full border text-caption font-body cursor-pointer ${checked ? 'border-sheikah-teal bg-sheikah-teal/15 text-sheikah-teal-deep' : 'border-ink-page-shadow text-ink-secondary'}`}
                      >
                        <input
                          type="checkbox"
                          className="sr-only"
                          checked={checked}
                          onChange={() => toggleCoopChild(c.id)}
                        />
                        {c.display_label || c.username}
                      </label>
                    );
                  })}
                </div>
                <div className="text-tiny text-ink-whisper mt-1">
                  Pick at least 2 — damage / collection pools across them.
                </div>
              </div>
            ) : (
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
            )}
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
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

          <label className="mt-3 flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={challenge.is_coop}
              onChange={(e) =>
                setChallenge({
                  ...challenge,
                  is_coop: e.target.checked,
                  coop_user_ids: e.target.checked ? challenge.coop_user_ids : [],
                  assigned_to: e.target.checked ? '' : challenge.assigned_to,
                })
              }
            />
            <span className="font-body text-body text-ink-primary">
              Co-op campaign (multiple kids on one shared quest)
            </span>
          </label>

          <details className="mt-3">
            <summary className="cursor-pointer font-display italic text-body text-ink-secondary">
              Advanced — narrow which actions count
            </summary>
            <div className="mt-2 space-y-2">
              <div className="font-script text-caption text-ink-whisper">
                Leave all unchecked to count every action. Checking some
                limits damage / collection to those triggers.
              </div>
              <div className="flex flex-wrap gap-1.5">
                {TRIGGER_OPTIONS.map(([slug, label]) => {
                  const checked = challenge.allowed_triggers.includes(slug);
                  return (
                    <label
                      key={slug}
                      className={`flex items-center gap-1.5 px-2 py-1 rounded-full border text-caption font-body cursor-pointer ${checked ? 'border-sheikah-teal bg-sheikah-teal/15 text-sheikah-teal-deep' : 'border-ink-page-shadow text-ink-secondary'}`}
                    >
                      <input
                        type="checkbox"
                        className="sr-only"
                        checked={checked}
                        onChange={() => toggleAllowedTrigger(slug)}
                      />
                      {label}
                    </label>
                  );
                })}
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={challenge.on_time_only}
                  onChange={(e) =>
                    setChallenge({ ...challenge, on_time_only: e.target.checked })
                  }
                />
                <span className="font-body text-body text-ink-secondary">
                  Only count homework submitted on time / early
                </span>
              </label>
            </div>
          </details>

          <details className="mt-3">
            <summary className="cursor-pointer font-display italic text-body text-ink-secondary">
              Skill XP fanout (optional)
            </summary>
            <div className="mt-2 space-y-2">
              <div className="font-script text-caption text-ink-whisper">
                Without tags the XP reward goes to no skill in particular.
                Tag 1-3 skills so kids see XP land where they earned it.
              </div>
              <SkillTagEditor
                skills={skills}
                value={challenge.skill_tags}
                onChange={(next) => setChallenge({ ...challenge, skill_tags: next })}
              />
            </div>
          </details>

          <Button
            onClick={handleIssueChallenge}
            disabled={
              (!challenge.is_coop && !challenge.assigned_to) ||
              (challenge.is_coop && challenge.coop_user_ids.length < 2) ||
              !challenge.name || !challenge.description || issuing
            }
            className="w-full mt-3"
          >
            {issuing ? 'Issuing…' : 'Issue the challenge'}
          </Button>
        </ParchmentCard>
      )}
    </div>
  );
}

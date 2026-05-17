import { motion } from 'framer-motion';
import { Lock, Play } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import RpgSprite from '../../components/rpg/RpgSprite';
import RuneBadge from '../../components/journal/RuneBadge';
import Button from '../../components/Button';
import { STATUS_TONE } from './trials.constants';

/**
 * QuestTile — one entry in a TrialsFolio grid. Renders four states based
 * on the `chapter` prop:
 *
 *   - `available` — full sprite + name + meta + Begin button (when no
 *     active quest blocks starting).
 *   - `underway` — never rendered here (active quest renders as
 *     ActiveQuestFolio instead). Defensive fallback to `available` look.
 *   - `closed` — sprite + name + status chip (completed / expired /
 *     failed) + progress at close.
 *   - `locked` — debossed silhouette + lock chip + the required badge
 *     name as the unlock hint. Same intaglio vocabulary the Reliquary
 *     uses for unearned sigils.
 *
 * Domain-agnostic decoration only — no calls. Parent passes `onBegin`
 * for the Begin click; tile decides whether to render it based on
 * `canBegin`.
 */
export default function QuestTile({
  quest,
  chapter,
  onBegin,
  onSelect,
  canBegin,
  starting = false,
}) {
  if (chapter === 'locked') {
    return <LockedTile quest={quest} onSelect={onSelect} />;
  }
  // Underway + Closed both render Quest rows (definition is nested), so
  // they share the progress-tile shape. The ActiveQuestFolio above the
  // codex carries the prominent active-quest UI; the underway tile here
  // is the minimal echo in the codex shelf.
  if (chapter === 'closed' || chapter === 'underway') {
    return <ProgressTile quest={quest} onSelect={onSelect} />;
  }
  return (
    <AvailableTile
      quest={quest}
      canBegin={canBegin}
      starting={starting}
      onBegin={onBegin}
      onSelect={onSelect}
    />
  );
}

function AvailableTile({ quest, canBegin, starting, onBegin, onSelect }) {
  // `available` rows are QuestDefinitions; their fields are flat.
  const def = quest;
  const coop = (quest?.participants?.length || 0) > 1;
  return (
    <motion.div whileHover={{ y: -2 }}>
      <ParchmentCard
        as="article"
        aria-label={`${def.name} — available trial`}
        className="text-center transition-all"
      >
        <div className="flex items-center justify-center h-16 mb-2">
          <RpgSprite
            spriteKey={def.sprite_key}
            icon={def.icon}
            size={56}
            alt={def.name}
          />
        </div>
        <button
          type="button"
          onClick={() => onSelect?.(def)}
          className="font-display text-base text-ink-primary leading-tight w-full hover:text-sheikah-teal-deep transition-colors text-left"
        >
          {def.name}
        </button>
        <p className="font-script text-micro text-ink-whisper mt-1 line-clamp-2 min-h-[2em]">
          {def.description}
        </p>
        <div className="mt-2 flex flex-wrap justify-center items-center gap-1">
          <RuneBadge tone="teal" size="sm">{def.quest_type_display ?? def.quest_type}</RuneBadge>
          {coop && <RuneBadge tone="royal" size="sm">co-op</RuneBadge>}
        </div>
        <div className="mt-1 font-rune text-tiny text-ink-whisper tabular-nums">
          target {def.target_value} · {def.duration_days}d
          {def.coin_reward > 0 && <span> · {def.coin_reward}c</span>}
          {def.xp_reward > 0 && <span> · {def.xp_reward}xp</span>}
        </div>
        {canBegin && onBegin && (
          <Button
            size="sm"
            onClick={() => onBegin(def)}
            disabled={starting}
            className="mt-2 inline-flex items-center gap-1"
          >
            <Play size={12} /> {starting ? 'Starting…' : 'Begin'}
          </Button>
        )}
      </ParchmentCard>
    </motion.div>
  );
}

function ProgressTile({ quest, onSelect }) {
  const def = quest.definition || {};
  const tone = STATUS_TONE[quest.status] || 'ink';
  const target = quest.effective_target ?? def.target_value ?? 0;
  return (
    <button
      type="button"
      onClick={() => onSelect?.(quest)}
      aria-label={`${def.name} — ${quest.status}`}
      className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl"
    >
      <ParchmentCard className="text-center cursor-pointer transition-all">
        <div className="flex items-center justify-center h-14 mb-1">
          <RpgSprite
            spriteKey={def.sprite_key}
            icon={def.icon}
            size={48}
            alt={def.name}
          />
        </div>
        <div className="font-display text-sm text-ink-primary leading-tight line-clamp-2">
          {def.name}
        </div>
        <div className="mt-1 flex justify-center">
          <RuneBadge tone={tone} size="sm">{quest.status}</RuneBadge>
        </div>
        <div className="font-rune text-tiny text-ink-whisper tabular-nums mt-1">
          {quest.current_progress}/{target}
        </div>
      </ParchmentCard>
    </button>
  );
}

function LockedTile({ quest, onSelect }) {
  const def = quest;
  const hint = def.required_badge_name
    ? `earn the ${def.required_badge_name} seal to unlock`
    : 'earn the gating seal to unlock';
  return (
    <button
      type="button"
      onClick={() => onSelect?.(def)}
      aria-label={`${def.name} — locked`}
      className="block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-sheikah-teal-deep rounded-2xl"
    >
      <ParchmentCard className="text-center opacity-80 hover:opacity-100 transition-all">
        <div className="flex items-center justify-center h-14 mb-1">
          <span
            aria-hidden="true"
            style={{ filter: 'brightness(0)' }}
            className="text-4xl"
          >
            {def.icon || '🔒'}
          </span>
        </div>
        <div className="font-display text-sm text-ink-secondary leading-tight line-clamp-2">
          {def.name}
        </div>
        <div className="font-script text-tiny text-ink-whisper mt-1 inline-flex items-center gap-1">
          <Lock size={10} aria-hidden="true" />
          {hint}
        </div>
      </ParchmentCard>
    </button>
  );
}

import { Shield } from 'lucide-react';
import { motion } from 'framer-motion';
import QuestFolio from '../quests/QuestFolio';
import RpgSprite from '../../components/rpg/RpgSprite';
import RuneBadge from '../../components/journal/RuneBadge';
import { formatDate } from '../../utils/format';
import { STATUS_TONE } from './trials.constants';

/**
 * ActiveQuestFolio — wraps the current Quest in the QuestFolio verso/recto
 * shell shared by Ventures · Duties · Study · Rituals · Movement. The
 * verso carries the illuminated drop-cap + foil title + quest-type chip
 * + progress; the recto carries party contributions, rage shield, rewards
 * preview, and end date.
 *
 * Reuses pages/quests/QuestFolio.jsx — no new layout, just a new caller.
 */
export default function ActiveQuestFolio({ quest }) {
  if (!quest) return null;

  const def = quest.definition || {};
  const initial = (def.name || 'T').trim().charAt(0).toUpperCase() || 'T';
  const isBoss = def.quest_type === 'boss';
  const target = quest.effective_target ?? def.target_value ?? 0;
  const pct = quest.progress_percent ?? 0;
  const coop = (quest.participants?.length || 0) > 1;
  const stats = [
    { label: isBoss ? 'damage' : 'collected', value: `${quest.current_progress}/${target}` },
  ];
  if (def.coin_reward > 0) {
    stats.push({ label: 'coins', value: def.coin_reward });
  }
  if (def.xp_reward > 0) {
    stats.push({ label: 'xp', value: def.xp_reward });
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <QuestFolio
        letter={initial}
        title={def.name}
        kicker="· trial under way ·"
        meta={(
          <span className="inline-flex items-center gap-1.5">
            <RuneBadge tone={STATUS_TONE[quest.status] || 'teal'} size="sm">
              {quest.status}
            </RuneBadge>
            <RuneBadge tone="royal" size="sm">
              {def.quest_type_display ?? def.quest_type}
            </RuneBadge>
            {coop && <RuneBadge tone="moss" size="sm">co-op</RuneBadge>}
          </span>
        )}
        stats={stats}
        progressPct={pct}
        progressLabel={`${pct}% · ends ${formatDate(quest.end_date)}`}
      >
        <RectoBody quest={quest} />
      </QuestFolio>
    </motion.div>
  );
}

function RectoBody({ quest }) {
  const def = quest.definition || {};
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <div className="shrink-0">
          <RpgSprite
            spriteKey={def.sprite_key}
            icon={def.icon}
            size={56}
            alt={def.name}
          />
        </div>
        <p className="font-body text-body text-ink-secondary leading-snug">
          {def.description}
        </p>
      </div>

      {quest.participants?.length > 1 && (
        <PartyTable quest={quest} />
      )}

      {quest.rage_shield > 0 && (
        <div className="flex items-center gap-2 font-script text-body text-ember-deep bg-ember/10 rounded-lg p-2 border border-ember/40">
          <Shield size={14} aria-hidden="true" /> Boss raged! +{quest.rage_shield} shield
        </div>
      )}

      {(def.coin_reward > 0 || def.xp_reward > 0 || def.reward_items?.length > 0) && (
        <div className="font-script text-body text-ink-secondary">
          <span className="text-ink-whisper uppercase tracking-wider text-caption">
            rewards ·{' '}
          </span>
          {def.coin_reward > 0 && (
            <span className="mr-2">{def.coin_reward} coins</span>
          )}
          {def.xp_reward > 0 && (
            <span className="mr-2">{def.xp_reward} XP</span>
          )}
          {def.reward_items?.map((r) => (
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
      )}
    </div>
  );
}

function PartyTable({ quest }) {
  return (
    <div>
      <div className="font-script text-body text-ink-primary mb-1">Party</div>
      <div className="space-y-1">
        {quest.participants.map((p) => {
          const pct = quest.current_progress > 0
            ? Math.round((p.contribution / quest.current_progress) * 100)
            : 0;
          return (
            <div key={p.id} className="flex items-center gap-2">
              <span className="font-script text-caption text-ink-secondary w-20 shrink-0 truncate">
                {p.user_name}
              </span>
              <div className="flex-1 h-2 rounded-full bg-ink-page-shadow/60 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-moss-deep to-moss"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="font-rune text-caption text-ink-whisper tabular-nums w-16 text-right shrink-0">
                {p.contribution} ({pct}%)
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

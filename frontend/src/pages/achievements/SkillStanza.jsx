import { motion, useReducedMotion } from 'framer-motion';
import { Lock } from 'lucide-react';
import QuillProgress from '../../components/QuillProgress';
import PrereqChain from './PrereqChain';
import { PROGRESS_TIER, tierForProgress } from './mastery.constants';
import { XP_THRESHOLDS } from './skillTree.constants';

/**
 * SkillStanza — the horizontal row replacing the old SkillCard. Each stanza
 * is a single line of the codex: accent bar keyed to progression tier, glyph,
 * name + level name, optional prereq chain, inline quill XP bar, level chip.
 *
 * Stagger animates on mount (capped at 8 rows / 350ms) so large subjects
 * ink-in rhythmically without swamping the thread.
 */
export default function SkillStanza({ skill, index = 0, onSelect }) {
  const reduceMotion = useReducedMotion();
  const nextThreshold = XP_THRESHOLDS[skill.level + 1] ?? XP_THRESHOLDS[6];
  const currentThreshold = XP_THRESHOLDS[skill.level] ?? 0;
  const span = Math.max(1, nextThreshold - currentThreshold);
  const progressPct = skill.unlocked
    ? Math.min(100, ((skill.xp_points - currentThreshold) / span) * 100)
    : 0;
  const tier = tierForProgress({
    unlocked: !!skill.unlocked,
    progressPct,
    level: skill.level,
  });
  const levelName = skill.level_names?.[String(skill.level)] || '';
  const maxed = skill.level >= 6;

  return (
    <motion.button
      type="button"
      layout
      initial={reduceMotion ? false : { opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        delay: reduceMotion ? 0 : Math.min(index, 7) * 0.05,
        duration: reduceMotion ? 0 : 0.35,
        ease: [0.4, 0, 0.2, 1],
      }}
      onClick={() => onSelect?.(skill)}
      className={`w-full relative text-left pl-4 pr-3 py-3 rounded-xl border border-ink-page-shadow bg-ink-page-aged shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset,0_2px_8px_-6px_rgba(45,31,21,0.35)] cursor-pointer active:scale-[0.99] transition-transform overflow-hidden ${
        skill.unlocked ? '' : 'opacity-70'
      }`}
    >
      <span
        data-accent-bar="true"
        aria-hidden="true"
        className={`absolute inset-y-2 left-0 w-1 rounded-r-full ${tier.bar}`}
      />
      <div className="flex items-center gap-3">
        <span aria-hidden="true" className="text-2xl leading-none shrink-0">
          {skill.icon || '✦'}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-display text-body md:text-lede font-semibold text-ink-primary truncate">
              {skill.name}
            </span>
            {!skill.unlocked && (
              <Lock size={14} className="text-ink-whisper shrink-0" aria-hidden="true" />
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-caption text-ink-whisper truncate">
              {skill.unlocked
                ? levelName || `Level ${skill.level}`
                : 'Locked · forge prerequisites first'}
            </span>
            {skill.prerequisites?.length > 0 && (
              <PrereqChain prerequisites={skill.prerequisites} />
            )}
          </div>
        </div>
        <div className="shrink-0 text-right">
          <div
            className={`font-display text-lede font-bold leading-none ${
              maxed ? 'text-gold-leaf' : tier.chip
            }`}
          >
            L{skill.level}
          </div>
          {maxed && (
            <div className="text-micro font-rune uppercase tracking-wider text-ember-deep mt-0.5">
              mastery
            </div>
          )}
        </div>
      </div>

      {skill.unlocked && (
        <div className="mt-2.5 pl-1">
          <QuillProgress
            value={progressPct}
            color={tier.bar}
            aria-label={`${skill.name} XP progress toward level ${Math.min(skill.level + 1, 6)}`}
          />
          <div className="flex items-center justify-between text-caption text-ink-whisper mt-1">
            <span className="font-rune text-micro uppercase tracking-wider">
              {skill.xp_points.toLocaleString()} XP
            </span>
            {!maxed && (
              <span className="font-rune text-micro uppercase tracking-wider">
                {(nextThreshold - skill.xp_points).toLocaleString()} to L{skill.level + 1}
              </span>
            )}
          </div>
        </div>
      )}
    </motion.button>
  );
}

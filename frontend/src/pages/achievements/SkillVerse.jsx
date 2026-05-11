import { motion, useReducedMotion } from 'framer-motion';
import { Lock } from 'lucide-react';
import IlluminatedVersal from '../../components/atlas/IlluminatedVersal';
import PrereqChain from './PrereqChain';
import { tierForProgress } from '../../components/atlas/mastery.constants';
import { XP_THRESHOLDS } from './skillTree.constants';

/**
 * SkillVerse — a single illuminated row in the Folio recto. The skill's
 * drop-capital fills with gilt as XP accrues; a thin gilt hairline under
 * the level chip encodes progress-to-next-level. The verse reads as a
 * line of manuscript text rather than a form row. Stagger animates on
 * mount (cap at 8 so large subjects don't swamp the thread).
 */
export default function SkillVerse({ skill, index = 0, onSelect }) {
  const reduceMotion = useReducedMotion();
  const nextThreshold = XP_THRESHOLDS[skill.level + 1] ?? XP_THRESHOLDS[6];
  const currentThreshold = XP_THRESHOLDS[skill.level] ?? 0;
  const span = Math.max(1, nextThreshold - currentThreshold);
  const progressPct = skill.unlocked
    ? Math.max(0, Math.min(100, ((skill.xp_points - currentThreshold) / span) * 100))
    : 0;
  const tier = tierForProgress({
    unlocked: !!skill.unlocked,
    progressPct,
    level: skill.level,
  });
  const levelName = skill.level_names?.[String(skill.level)] || '';
  const maxed = skill.level >= 6;
  const recentlyGilded = skill.unlocked && progressPct >= 95;

  const ariaLabel = !skill.unlocked
    ? `${skill.name}, locked — requires ${(skill.prerequisites || []).map((p) => p.skill_name).join(', ') || 'prerequisites'}`
    : maxed
      ? `${skill.name}, level ${skill.level}${levelName ? ` (${levelName})` : ''}, mastery sealed`
      : `${skill.name}, level ${skill.level}${levelName ? ` (${levelName})` : ''}, ${Math.round(progressPct)}% toward level ${skill.level + 1}`;

  return (
    <motion.button
      type="button"
      layout
      initial={reduceMotion ? false : { opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{
        delay: reduceMotion ? 0 : Math.min(index, 7) * 0.045,
        duration: reduceMotion ? 0 : 0.35,
        ease: [0.4, 0, 0.2, 1],
      }}
      onClick={() => onSelect?.(skill)}
      aria-label={ariaLabel}
      data-skill-verse="true"
      data-locked={skill.unlocked ? 'false' : 'true'}
      className={`group w-full relative text-left flex items-center gap-3 px-3 py-2.5 rounded-lg border border-ink-page-shadow bg-ink-page-aged shadow-[0_1px_0_0_var(--color-ink-page-rune-glow)_inset,0_2px_6px_-5px_rgba(45,31,21,0.3)] cursor-pointer transition-colors hover:bg-ink-page-rune-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold-leaf/60 ${
        skill.unlocked ? '' : 'opacity-75'
      } ${recentlyGilded ? 'animate-gilded-glint' : ''}`}
    >
      <IlluminatedVersal
        letter={skill.name?.[0] || '✦'}
        progressPct={progressPct}
        tier={tier}
        size="md"
      />

      <span className="flex-1 min-w-0">
        <span className="flex items-center gap-1.5">
          <span className="font-display italic font-semibold text-body md:text-lede text-ink-primary truncate">
            {skill.name}
          </span>
          {!skill.unlocked && (
            <Lock size={13} className="text-ink-whisper shrink-0" aria-hidden="true" />
          )}
          {skill.icon && (
            <span aria-hidden="true" className="text-sm leading-none opacity-70 shrink-0">
              {skill.icon}
            </span>
          )}
        </span>
        <span className="flex items-center gap-2 mt-0.5">
          <span className="font-script text-caption text-ink-whisper truncate">
            {skill.unlocked
              ? levelName || `Level ${skill.level}`
              : 'locked — forge prerequisites first'}
          </span>
          {skill.prerequisites?.length > 0 && (
            <PrereqChain prerequisites={skill.prerequisites} />
          )}
        </span>
      </span>

      {/* Level strap — right-aligned L{n} with a gilt hairline underneath
          whose length encodes progress to next level. */}
      <span className="shrink-0 flex flex-col items-end gap-1 min-w-[52px]">
        <span
          className={`font-display italic font-bold leading-none text-lede ${
            maxed ? 'text-gold-leaf' : tier.chip
          }`}
        >
          L{skill.level}
        </span>
        {skill.unlocked && !maxed && (
          <span
            aria-hidden="true"
            data-level-strap="true"
            className="relative h-px w-10 bg-ink-page-shadow/50 overflow-hidden"
          >
            <span
              className={`absolute inset-y-0 left-0 ${tier.bar}`}
              style={{
                width: `${progressPct}%`,
                transition: reduceMotion ? 'none' : 'width 550ms cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            />
          </span>
        )}
        {maxed && (
          <span className="text-micro font-rune uppercase tracking-wider text-ember-deep">
            mastery
          </span>
        )}
      </span>
    </motion.button>
  );
}

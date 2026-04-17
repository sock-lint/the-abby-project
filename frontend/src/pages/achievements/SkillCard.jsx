import { motion } from 'framer-motion';
import { Lock, Unlock } from 'lucide-react';
import ParchmentCard from '../../components/journal/ParchmentCard';
import ProgressBar from '../../components/ProgressBar';
import { XP_THRESHOLDS } from './skillTree.constants';

export default function SkillCard({ skill, onSelect, index }) {
  const nextThreshold = XP_THRESHOLDS[skill.level + 1] || XP_THRESHOLDS[6];
  const currentThreshold = XP_THRESHOLDS[skill.level] || 0;
  const progress = nextThreshold > currentThreshold
    ? ((skill.xp_points - currentThreshold) / (nextThreshold - currentThreshold)) * 100
    : 100;
  const levelName = skill.level_names[String(skill.level)] || '';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.04 }}
    >
      <ParchmentCard
        className={`${!skill.unlocked ? 'opacity-40' : ''} cursor-pointer active:scale-[0.98] transition-transform`}
        onClick={onSelect}
      >
        <div className="flex items-center gap-3 mb-2">
          <div className="text-2xl">{skill.icon}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-medium text-sm truncate">{skill.name}</span>
              {!skill.unlocked && <Lock size={12} className="text-ink-whisper shrink-0" />}
              {skill.unlocked && skill.is_locked_by_default && (
                <Unlock size={12} className="text-sheikah-teal-deep shrink-0" />
              )}
            </div>
            <div className="text-xs text-ink-whisper">
              {skill.unlocked
                ? `Level ${skill.level}${levelName ? ` — ${levelName}` : ''}`
                : 'Locked'}
            </div>
          </div>
          <div className="font-display text-sm font-bold text-ink-whisper shrink-0">
            L{skill.level}
          </div>
        </div>
        {skill.unlocked && (
          <div>
            <div className="flex justify-between text-xs text-ink-whisper mb-1">
              <span>{skill.xp_points} XP</span>
              <span>{nextThreshold} XP</span>
            </div>
            <ProgressBar
              value={Math.min(100, progress)}
              aria-label={`${skill.name} XP progress`}
            />
          </div>
        )}
        {!skill.unlocked && skill.prerequisites?.length > 0 && (
          <div className="text-xs text-ink-whisper mt-1">
            Requires: {skill.prerequisites.map((p) =>
              `${p.skill_name} L${p.required_level}${p.met ? ' ✓' : ''}`,
            ).join(', ')}
          </div>
        )}
      </ParchmentCard>
    </motion.div>
  );
}

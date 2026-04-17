import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getSkillTree } from '../../api';
import BottomSheet from '../../components/BottomSheet';
import ParchmentCard from '../../components/journal/ParchmentCard';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import ProgressBar from '../../components/ProgressBar';
import TabButton from '../../components/TabButton';
import SkillCard from './SkillCard';
import { XP_THRESHOLDS } from './skillTree.constants';

function SkillDetailSheet({ skill, onClose }) {
  const nextThreshold = XP_THRESHOLDS[skill.level + 1] || XP_THRESHOLDS[6];
  const currentThreshold = XP_THRESHOLDS[skill.level] || 0;
  const xpInLevel = skill.xp_points - currentThreshold;
  const xpNeeded = nextThreshold - currentThreshold;
  const progress = xpNeeded > 0 ? (xpInLevel / xpNeeded) * 100 : 100;
  const levelNames = Object.entries(skill.level_names).sort(([a], [b]) => Number(a) - Number(b));

  return (
    <BottomSheet title={skill.name} onClose={onClose}>
      <div className="text-center">
        <div className="text-5xl mb-3">{skill.icon}</div>
        <div className="text-sm text-ink-whisper mb-3">
          {skill.description || 'No description yet.'}
        </div>

        <div className="flex justify-center gap-6 mb-4">
          <div className="text-center">
            <div className="font-display text-2xl font-bold text-sheikah-teal-deep">{skill.level}</div>
            <div className="text-xs text-ink-whisper">Level</div>
          </div>
          <div className="text-center">
            <div className="font-display text-2xl font-bold text-ink-primary">{skill.xp_points}</div>
            <div className="text-xs text-ink-whisper">XP</div>
          </div>
        </div>

        {skill.level_names[String(skill.level)] && (
          <div className="text-sm font-medium text-sheikah-teal-deep mb-3">
            {skill.level_names[String(skill.level)]}
          </div>
        )}

        {skill.unlocked && (
          <div className="mb-4">
            <div className="flex justify-between text-xs text-ink-whisper mb-1">
              <span>{xpInLevel} / {xpNeeded} XP to next level</span>
            </div>
            <ProgressBar
              value={Math.min(100, progress)}
              aria-label={`${skill.name} progress to level ${skill.level + 1}`}
            />
          </div>
        )}

        {levelNames.length > 0 && (
          <div className="text-left space-y-1 mb-3">
            <div className="text-xs font-medium text-ink-whisper uppercase tracking-wide mb-2">Level Roadmap</div>
            {levelNames.map(([lvl, name]) => (
              <div
                key={lvl}
                className={`flex items-center gap-2 text-sm ${
                  Number(lvl) <= skill.level ? 'text-sheikah-teal-deep' : 'text-ink-whisper'
                }`}
              >
                <span className="font-display text-xs w-6">L{lvl}</span>
                <span>{name}</span>
              </div>
            ))}
          </div>
        )}

        {skill.prerequisites?.length > 0 && (
          <div className="text-left space-y-1">
            <div className="text-xs font-medium text-ink-whisper uppercase tracking-wide mb-2">Prerequisites</div>
            {skill.prerequisites.map((p, i) => (
              <div
                key={i}
                className={`flex items-center justify-between text-sm ${
                  p.met ? 'text-moss' : 'text-ink-whisper'
                }`}
              >
                <span>{p.skill_name} Level {p.required_level}</span>
                <span>{p.met ? '✓' : '✗'}</span>
              </div>
            ))}
          </div>
        )}

        {!skill.unlocked && (
          <div className="mt-3 text-xs text-ink-whisper italic">This skill is locked</div>
        )}
      </div>
    </BottomSheet>
  );
}

export default function SkillTreeView({ categories }) {
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState(null);

  const loadTree = async (catId) => {
    if (selectedCategory === catId) {
      setSelectedCategory(null);
      setTree(null);
      return;
    }
    setSelectedCategory(catId);
    setTreeLoading(true);
    try {
      const data = await getSkillTree(catId);
      setTree(data);
    } catch {
      setTree(null);
    }
    setTreeLoading(false);
  };

  return (
    <div>
      <h2 className="font-display text-lg font-bold mb-3">Skill Tree</h2>
      <div
        className="flex gap-2 overflow-x-auto pb-2 mb-4 scrollbar-hide"
        style={{
          maskImage: 'linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent)',
          WebkitMaskImage: 'linear-gradient(to right, transparent, black 24px, black calc(100% - 24px), transparent)',
        }}
      >
        {categories.map((cat) => (
          <TabButton
            key={cat.id}
            active={selectedCategory === cat.id}
            onClick={() => loadTree(cat.id)}
            className="shrink-0"
          >
            <span className="flex items-center gap-1.5">
              <span>{cat.icon}</span>
              <span>{cat.name}</span>
            </span>
          </TabButton>
        ))}
      </div>

      {treeLoading && <Loader />}

      {!tree && !treeLoading && (
        <EmptyState>
          <div className="text-sm font-medium text-ink-primary mb-1">Pick a category above</div>
          <div className="text-xs">Tap a category to explore your skill tree</div>
        </EmptyState>
      )}

      {tree && !treeLoading && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
          <ParchmentCard className="flex items-center justify-between !p-3 md:!p-4">
            <div className="flex items-center gap-2">
              <span className="text-xl md:text-2xl">{tree.category.icon}</span>
              <div>
                <div className="font-bold text-sm md:text-base">{tree.category.name}</div>
                <div className="text-xs text-ink-whisper">
                  Level {tree.summary.level} · {tree.summary.total_xp} XP
                </div>
              </div>
            </div>
          </ParchmentCard>

          {tree.subjects.map((subject) => (
            <div key={subject.id} className="space-y-2 border-l-2 border-sheikah-teal-deep/30 pl-3">
              {subject.name && (
                <div className="flex items-center justify-between py-2 sticky top-0 bg-ink-page/95 backdrop-blur-sm z-10 -ml-3 pl-4 pr-1 rounded-r-lg">
                  <div className="flex items-center gap-2">
                    {subject.icon && <span>{subject.icon}</span>}
                    <span className="font-display text-sm font-bold text-ink-primary">{subject.name}</span>
                  </div>
                  {subject.summary && (
                    <span className="text-xs text-ink-whisper">
                      L{subject.summary.level} · {subject.summary.total_xp} XP
                    </span>
                  )}
                </div>
              )}
              <div className="grid md:grid-cols-2 gap-3">
                {subject.skills.map((skill, i) => (
                  <SkillCard
                    key={skill.id}
                    skill={skill}
                    index={i}
                    onSelect={() => setSelectedSkill(skill)}
                  />
                ))}
              </div>
            </div>
          ))}
        </motion.div>
      )}

      <AnimatePresence>
        {selectedSkill && (
          <SkillDetailSheet skill={selectedSkill} onClose={() => setSelectedSkill(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}

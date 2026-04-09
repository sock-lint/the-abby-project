import { useState } from 'react';
import { motion } from 'framer-motion';
import { Lock, Unlock } from 'lucide-react';
import { getAchievementsSummary, getCategories, getSkillTree } from '../api';
import { useApi } from '../hooks/useApi';
import Card from '../components/Card';
import Loader from '../components/Loader';

const rarityColors = {
  common: 'border-rarity-common/30 bg-rarity-common/5',
  uncommon: 'border-rarity-uncommon/30 bg-rarity-uncommon/5',
  rare: 'border-rarity-rare/30 bg-rarity-rare/5',
  epic: 'border-rarity-epic/30 bg-rarity-epic/5',
  legendary: 'border-rarity-legendary/30 bg-rarity-legendary/5',
};

const rarityText = {
  common: 'text-rarity-common',
  uncommon: 'text-rarity-uncommon',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

const XP_THRESHOLDS = { 0: 0, 1: 100, 2: 300, 3: 600, 4: 1000, 5: 1500, 6: 2500 };

export default function Achievements() {
  const { data: summary, loading } = useApi(getAchievementsSummary);
  const { data: categoriesData } = useApi(getCategories);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [tree, setTree] = useState(null);
  const [treeLoading, setTreeLoading] = useState(false);

  const categories = categoriesData?.results || categoriesData || [];

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
    } catch { setTree(null); }
    setTreeLoading(false);
  };

  if (loading) return <Loader />;
  if (!summary) return null;

  const earnedBadges = summary.badges_earned || [];
  const earnedIds = new Set(earnedBadges.map(ub => ub.badge.id));

  return (
    <div className="space-y-6">
      <h1 className="font-heading text-2xl font-bold">Achievements</h1>

      {/* Badge Collection */}
      <div>
        <h2 className="font-heading text-lg font-bold mb-3">
          Badges ({earnedBadges.length}/{summary.total_badges})
        </h2>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3">
          {earnedBadges.map((ub, i) => (
            <motion.div
              key={ub.id}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ delay: i * 0.03 }}
            >
              <Card className={`text-center ${rarityColors[ub.badge.rarity]}`}>
                <div className="text-3xl mb-1">{ub.badge.icon}</div>
                <div className="text-[10px] font-medium leading-tight">{ub.badge.name}</div>
                <div className={`text-[9px] capitalize ${rarityText[ub.badge.rarity]}`}>{ub.badge.rarity}</div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>

      {/* Skill Tree */}
      <div>
        <h2 className="font-heading text-lg font-bold mb-3">Skill Tree</h2>
        <div className="flex gap-2 overflow-x-auto pb-2 mb-4">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => loadTree(cat.id)}
              className={`shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-colors border ${
                selectedCategory === cat.id
                  ? 'border-amber-primary bg-amber-primary/10 text-amber-highlight'
                  : 'border-forge-border bg-forge-card text-forge-text-dim hover:text-forge-text'
              }`}
            >
              <span>{cat.icon}</span>
              <span>{cat.name}</span>
            </button>
          ))}
        </div>

        {treeLoading && <Loader />}

        {tree && !treeLoading && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
            <Card className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-2xl">{tree.category.icon}</span>
                <div>
                  <div className="font-bold">{tree.category.name}</div>
                  <div className="text-xs text-forge-text-dim">
                    Level {tree.summary.level} | {tree.summary.total_xp} XP
                  </div>
                </div>
              </div>
            </Card>

            {(tree.subjects || [{ id: null, name: '', skills: tree.skills, summary: tree.summary }]).map((subject) => (
              <div key={subject.id ?? 'flat'} className="space-y-2">
                {subject.name && (
                  <div className="flex items-center justify-between px-1">
                    <div className="flex items-center gap-2">
                      {subject.icon && <span>{subject.icon}</span>}
                      <span className="font-heading text-sm font-bold text-forge-text">{subject.name}</span>
                    </div>
                    {subject.summary && (
                      <span className="text-[10px] text-forge-text-dim">
                        L{subject.summary.level} · {subject.summary.total_xp} XP
                      </span>
                    )}
                  </div>
                )}
                <div className="grid md:grid-cols-2 gap-3">
                  {subject.skills.map((skill) => {
                const nextThreshold = XP_THRESHOLDS[skill.level + 1] || XP_THRESHOLDS[6];
                const currentThreshold = XP_THRESHOLDS[skill.level] || 0;
                const progress = nextThreshold > currentThreshold
                  ? ((skill.xp_points - currentThreshold) / (nextThreshold - currentThreshold)) * 100
                  : 100;
                const levelName = skill.level_names[String(skill.level)] || '';

                return (
                  <motion.div key={skill.id} layout>
                    <Card className={`${!skill.unlocked ? 'opacity-40' : ''}`}>
                      <div className="flex items-center gap-3 mb-2">
                        <div className="text-2xl">{skill.icon}</div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-sm">{skill.name}</span>
                            {!skill.unlocked && <Lock size={12} className="text-forge-text-dim" />}
                            {skill.unlocked && skill.is_locked_by_default && (
                              <Unlock size={12} className="text-amber-highlight" />
                            )}
                          </div>
                          <div className="text-xs text-forge-text-dim">
                            {skill.unlocked
                              ? `Level ${skill.level}${levelName ? ` — ${levelName}` : ''}`
                              : 'Locked'
                            }
                          </div>
                        </div>
                        <div className="font-heading text-sm font-bold text-forge-text-dim">
                          L{skill.level}
                        </div>
                      </div>
                      {skill.unlocked && (
                        <div>
                          <div className="flex justify-between text-[10px] text-forge-text-dim mb-1">
                            <span>{skill.xp_points} XP</span>
                            <span>{nextThreshold} XP</span>
                          </div>
                          <div className="h-1.5 bg-forge-muted rounded-full overflow-hidden">
                            <motion.div
                              className="h-full bg-amber-primary rounded-full"
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.min(100, progress)}%` }}
                            />
                          </div>
                        </div>
                      )}
                      {!skill.unlocked && skill.prerequisites?.length > 0 && (
                        <div className="text-[10px] text-forge-text-dim mt-1">
                          Requires: {skill.prerequisites.map(p =>
                            `${p.skill_name} L${p.required_level}${p.met ? ' ✓' : ''}`
                          ).join(', ')}
                        </div>
                      )}
                    </Card>
                  </motion.div>
                );
                  })}
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </div>
    </div>
  );
}

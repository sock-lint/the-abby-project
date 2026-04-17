import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getSkillTree } from '../../api';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import CategoryRibbon from './CategoryRibbon';
import CategoryCapitulare from './CategoryCapitulare';
import ChapterRubric from './ChapterRubric';
import SkillStanza from './SkillStanza';
import SkillDetailSheet from './SkillDetailSheet';

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

  if (!categories?.length) {
    return (
      <EmptyState>
        <div className="text-body font-medium text-ink-primary mb-1">
          No skill categories yet
        </div>
        <div className="text-caption">
          A parent can weave them into the atlas from Manage.
        </div>
      </EmptyState>
    );
  }

  return (
    <div>
      <CategoryRibbon
        categories={categories}
        activeId={selectedCategory}
        onSelect={loadTree}
      />

      {treeLoading && <Loader />}

      {!tree && !treeLoading && (
        <EmptyState>
          <div className="text-body font-medium text-ink-primary mb-1">
            Pick a chapter above
          </div>
          <div className="text-caption">
            Tap a category pennant to leaf through its skills.
          </div>
        </EmptyState>
      )}

      {tree && !treeLoading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.35 }}
          className="space-y-4"
        >
          <CategoryCapitulare tree={tree} />

          {tree.subjects.map((subject, i) => (
            <section key={subject.id} className="space-y-2">
              <ChapterRubric index={i} subject={subject} />
              <div className="grid md:grid-cols-2 gap-2 md:gap-3">
                {subject.skills.map((skill, j) => (
                  <SkillStanza
                    key={skill.id}
                    skill={skill}
                    index={j}
                    onSelect={setSelectedSkill}
                  />
                ))}
              </div>
            </section>
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

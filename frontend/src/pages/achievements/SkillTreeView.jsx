import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { getSkillTree } from '../../api';
import EmptyState from '../../components/EmptyState';
import Loader from '../../components/Loader';
import FolioSpread from './FolioSpread';
import SkillDetailSheet from './SkillDetailSheet';
import TomeShelf from './TomeShelf';

/**
 * SkillTreeView — the Skills tab body. A thin orchestrator: the TomeShelf
 * picks a category, the FolioSpread renders that category's folio, and
 * SkillDetailSheet opens on verse selection.
 */
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
    <div className="space-y-4">
      <TomeShelf
        categories={categories}
        activeId={selectedCategory}
        onSelect={loadTree}
      />

      {treeLoading && <Loader />}

      {!tree && !treeLoading && (
        <EmptyState>
          <div className="text-body font-medium text-ink-primary mb-1">
            Pull a tome from the shelf
          </div>
          <div className="text-caption">
            Tap a spine above to open its folio and leaf through its skills.
          </div>
        </EmptyState>
      )}

      <AnimatePresence mode="wait">
        {tree && !treeLoading && (
          <motion.div
            key={tree.category?.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.35, ease: [0.4, 0, 0.2, 1] }}
          >
            <FolioSpread tree={tree} onSelectSkill={setSelectedSkill} />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {selectedSkill && (
          <SkillDetailSheet skill={selectedSkill} onClose={() => setSelectedSkill(null)} />
        )}
      </AnimatePresence>
    </div>
  );
}
